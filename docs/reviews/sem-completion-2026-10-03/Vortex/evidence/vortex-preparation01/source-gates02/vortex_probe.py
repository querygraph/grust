"""Run one admitted tiny Vortex control; retain every output and owned exit.

Root alone launches this script from the selected client venv and waits it.
The registered mode uses the exact Python reader, never a fabricated Rust format.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pyspark
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.connect.session import SparkSession
from vortex_models import (
    Attempt,
    Error,
    FilePin,
    PhysicalCheck,
    Plan,
    Receipt,
    ServerExit,
)

try:
    import vortex as vx
except ImportError:
    vx = None

try:
    from pysail.spark.datasource.vortex import VortexDataSource
except ImportError as import_error:
    ADAPTER_ERROR: str | None = str(import_error)
    VortexDataSource = None
else:
    ADAPTER_ERROR = None


@dataclass(frozen=True, slots=True)
class FixtureRow:
    id: int
    name: str | None
    score: float | None


ROWS = (
    FixtureRow(-(2**63), "alpha", -1.5),
    FixtureRow(-8, None, 1.5),
    FixtureRow(0, "beta", 0.0),
    FixtureRow(2, "beta-two", None),
    FixtureRow(5, "gamma", 1.5),
    FixtureRow(2**63 - 1, "delta", 3.0),
)
SCHEMA = pa.schema(
    [
        pa.field("id", pa.int64()),
        pa.field("name", pa.string()),
        pa.field("score", pa.float64()),
    ]
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def pin(path: Path) -> FilePin:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return FilePin(path=path, bytes=path.stat().st_size, sha256=digest)


def save(receipt: Receipt) -> None:
    path = receipt.plan.output_root / "receipt.json"
    temporary = path.with_suffix(".json.new")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n")
    temporary.replace(path)


def fail_signal(number: int, _frame: FrameType | None) -> None:
    raise TimeoutError(f"owned control interrupted by signal {number}")


def error(phase: str, failure: BaseException) -> Error:
    return Error(phase=phase, type=type(failure).__name__, message=str(failure))


def group_absent(pgid: int) -> bool:
    result = subprocess.run(
        ["ps", "-axo", "pgid="], capture_output=True, text=True, timeout=5, check=True
    )
    return str(pgid) not in {value.strip() for value in result.stdout.splitlines()}


def environment(plan: Plan) -> dict[str, str]:
    paths = [str(plan.python_purelib)]
    if plan.adapter_python_root is not None:
        paths.insert(0, str(plan.adapter_python_root))
    return {
        "PYTHONHOME": str(plan.python_home),
        "PYTHONPATH": os.pathsep.join(paths),
        "DYLD_LIBRARY_PATH": str(plan.python_library_directory),
        "SAIL_MODE": "local",
        "SAIL_EXPERIMENTAL_PROCESS_WORKERS": "0",
        "SAIL_EXPERIMENTAL_EXTENSIONS": "0",
        "SAIL_EXECUTION__DEFAULT_PARALLELISM": str(plan.threads),
        "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
        "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(plan.sail_pool_bytes),
        "TOKIO_WORKER_THREADS": str(plan.threads),
        "RAYON_NUM_THREADS": str(plan.threads),
        "TMPDIR": str(plan.output_root / "temporary"),
        "RUST_LOG": "info",
    }


def physical(
    receipt: Receipt,
    name: str,
    directory: Path,
    expected: tuple[FixtureRow, ...],
    columns: tuple[str, ...] = ("id", "name", "score"),
) -> None:
    files = sorted(directory.rglob("*.parquet"))
    if not files:
        raise ValueError(f"{name}: no physical Parquet files")
    tables = [pq.ParquetFile(path).read() for path in files]
    required = pa.schema([SCHEMA.field(column) for column in columns])
    for table in tables:
        if table.schema.names != list(columns) or any(
            table.schema.field(column).type != required.field(column).type
            for column in columns
        ):
            raise ValueError(f"{name}: raw names/types differ: {table.schema}")
    actual = pa.concat_tables(tables).to_pylist()
    actual.sort(key=lambda row: row["id"])
    wanted = [
        {column: getattr(row, column) for column in columns}
        for row in sorted(expected, key=lambda row: row.id)
    ]
    passed = actual == wanted and len({row["id"] for row in actual}) == len(actual)
    receipt.physical_checks.append(
        PhysicalCheck(
            name=name,
            directory=directory,
            rows=len(actual),
            expected_rows=len(wanted),
            physical_schemas=[str(table.schema) for table in tables],
            full_typed_rows_passed=passed,
            files=[pin(path) for path in files],
        )
    )
    save(receipt)
    if not passed:
        raise ValueError(f"{name}: full physical typed-row oracle mismatch")


def write_and_check(
    receipt: Receipt,
    name: str,
    frame: DataFrame,
    expected: tuple[FixtureRow, ...],
    columns: tuple[str, ...] = ("id", "name", "score"),
) -> None:
    directory = receipt.plan.output_root / name
    attempt = Attempt(name=name, directory=directory)
    receipt.attempts.append(attempt)
    save(receipt)
    try:
        frame.write.mode("error").parquet(directory.as_uri())
        attempt.outcome = "completed"
        physical(receipt, name, directory, expected, columns)
    except BaseException as failure:
        attempt.outcome = "error"
        attempt.error = error(name, failure)
        raise
    finally:
        save(receipt)


def observed_attempt(receipt: Receipt, name: str, operation: Callable[[], Any]) -> None:
    attempt = Attempt(name=name, directory=receipt.plan.output_root / name)
    receipt.attempts.append(attempt)
    save(receipt)
    try:
        operation()
        attempt.outcome = "completed"
    except Exception as failure:  # noqa: BLE001 - capability errors are observations
        attempt.outcome = "error"
        attempt.error = error(name, failure)
    finally:
        save(receipt)


def native_control(
    spark: SparkSession, receipt: Receipt, input_path: Path, table: pa.Table
) -> None:
    frame = spark.read.parquet(input_path.as_uri())
    write_and_check(receipt, "parquet-control", frame, ROWS)
    if vx is None:
        receipt.attempts.append(
            Attempt(
                name="native-format-read",
                outcome="not_admitted",
                error=Error(
                    phase="fixture",
                    type="MissingOptionalDependency",
                    message="vortex-data unavailable; no valid Vortex read fixture was fabricated",
                ),
            )
        )
    else:
        path = receipt.plan.output_root / "fixture.vortex"
        vx.io.write(table, str(path))
        observed_attempt(
            receipt,
            "native-format-read",
            lambda: write_and_check(
                receipt,
                "native-read-output",
                spark.read.format("vortex").option("path", str(path)).load(),
                ROWS,
            ),
        )
    observed_attempt(
        receipt,
        "native-format-write",
        lambda: (
            frame.write.format("vortex")
            .mode("error")
            .save(str(receipt.plan.output_root / "native-format-write"))
        ),
    )
    if receipt.attempts[-1].outcome == "completed":
        raise RuntimeError(
            "unexpected Vortex writer completed; raw result retained without a writer oracle"
        )
    receipt.outcome = "passed_native_format_control"


def registered_control(spark: SparkSession, receipt: Receipt, table: pa.Table) -> None:
    if vx is None or VortexDataSource is None:
        raise RuntimeError("adapter was not admitted")
    path = receipt.plan.output_root / "fixture.vortex"
    vx.io.write(table, str(path))
    roundtrip = pa.concat_tables(
        [batch.to_arrow_table() for batch in vx.open(str(path)).scan()]
    )
    if roundtrip.cast(SCHEMA).to_pylist() != table.to_pylist():
        raise ValueError("standalone Vortex full-row roundtrip mismatch")
    spark.dataSource.register(VortexDataSource)
    frame = spark.read.format("vortex").option("path", str(path)).load()
    write_and_check(receipt, "registered-all", frame, ROWS)
    write_and_check(
        receipt,
        "registered-equality",
        frame.filter(F.col("score") == 1.5),
        tuple(row for row in ROWS if row.score == 1.5),
    )
    write_and_check(
        receipt,
        "registered-range",
        frame.filter(F.col("id") >= 0),
        tuple(row for row in ROWS if row.id >= 0),
    )
    write_and_check(
        receipt,
        "registered-null-postfilter",
        frame.filter(F.col("name").isNull()),
        tuple(row for row in ROWS if row.name is None),
    )
    write_and_check(
        receipt,
        "registered-string-postfilter",
        frame.filter(F.col("name").startswith("beta")),
        tuple(
            row for row in ROWS if row.name is not None and row.name.startswith("beta")
        ),
    )
    write_and_check(
        receipt,
        "registered-projection",
        frame.select("id", "name"),
        ROWS,
        ("id", "name"),
    )
    observed_attempt(
        receipt,
        "registered-format-write",
        lambda: (
            frame.write.format("vortex")
            .mode("error")
            .save(str(receipt.plan.output_root / "registered-format-write"))
        ),
    )
    if receipt.attempts[-1].outcome == "completed":
        raise RuntimeError(
            "unexpected Vortex writer completed; raw result retained without a writer oracle"
        )
    receipt.outcome = "passed_registered_reader_control"


def close_server(server: subprocess.Popen[bytes], receipt: Receipt) -> None:
    proof = receipt.server
    if proof is None:
        # Popen succeeded but the initial journal failed: ownership still exists.
        if server.poll() is None:
            server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        raise RuntimeError("missing owned server launch proof")
    if server.poll() is None:
        proof.termination_requested = True
        server.terminate()
    try:
        proof.returncode = server.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proof.forced_cleanup = True
        server.kill()
        proof.returncode = server.wait(timeout=10)
    proof.wait_completed = True
    proof.closed_utc = utc()
    proof.group_absent = group_absent(proof.pgid)
    if (
        proof.forced_cleanup
        or not proof.group_absent
        or (not proof.termination_requested and proof.returncode != 0)
        or (
            proof.termination_requested and proof.returncode not in (0, -signal.SIGTERM)
        )
    ):
        raise RuntimeError(
            "owned server required forced cleanup or lacks natural group closure"
        )


def execute(path: Path) -> int:
    plan = Plan.model_validate_json(path.read_bytes())
    if Path(sys.prefix).resolve() != plan.venv.resolve():
        raise ValueError("interpreter is outside the declared venv")
    plan.output_root.mkdir(parents=True, exist_ok=False)
    (plan.output_root / "temporary").mkdir()
    receipt = Receipt(
        started_utc=utc(),
        configuration=pin(path),
        plan=plan,
        owner_pid=os.getpid(),
        python_version=sys.version,
        pyspark_version=pyspark.__version__,
        pyarrow_version=pa.__version__,
        adapter_import_error=ADAPTER_ERROR,
        environment=environment(plan),
    )
    server: subprocess.Popen[bytes] | None = None
    spark: SparkSession | None = None
    save(receipt)
    try:
        receipt.identities_before = [pin(value.path) for value in plan.pins]
        if receipt.identities_before != plan.pins:
            raise ValueError("an admitted physical file changed")
        mandatory = {
            Path(__file__).resolve(),
            Path(__file__).with_name("vortex_models.py").resolve(),
            plan.binary.resolve(),
            Path(sys.executable).resolve(),
        }
        if not mandatory.issubset({value.path.resolve() for value in plan.pins}):
            raise ValueError(
                "helper, models, binary and interpreter must be explicitly pinned"
            )
        if plan.mode == "registered_reader":
            if ADAPTER_ERROR is not None or VortexDataSource is None or vx is None:
                receipt.outcome = "not_admitted"
                return 2
            loaded_file = sys.modules[VortexDataSource.__module__].__file__
            if loaded_file is None:
                raise ValueError("loaded adapter has no physical module origin")
            adapter_file = Path(loaded_file).resolve()
            expected_adapter = plan.adapter_python_root
            if (
                expected_adapter is None
                or adapter_file
                != (expected_adapter / "pysail/spark/datasource/vortex.py").resolve()
            ):
                raise ValueError(
                    "loaded adapter is outside the declared exact source Python root"
                )
            if adapter_file not in {value.path.resolve() for value in plan.pins}:
                raise ValueError(
                    "loaded exact adapter module lacks its required source pin"
                )
            receipt.vortex_version = importlib.metadata.version("vortex-data")
        for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
            signal.signal(number, fail_signal)
        signal.alarm(plan.timeout_seconds)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        argv = [
            str(plan.binary),
            "spark",
            "server",
            "--ip",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        inherited = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SAIL_")
        }
        inherited.update(receipt.environment)
        with (plan.output_root / "server.log").open("xb") as log:
            server = subprocess.Popen(
                argv,
                env=inherited,
                cwd=plan.output_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            receipt.server = ServerExit(
                pid=server.pid, pgid=server.pid, argv=argv, launched_utc=utc()
            )
            receipt.server.pgid = os.getpgid(server.pid)
            if receipt.server.pgid != server.pid:
                raise ValueError("native server did not acquire its own process group")
            save(receipt)
        while True:
            if server.poll() is not None:
                raise RuntimeError(
                    f"server exited before readiness: {server.returncode}"
                )
            with socket.socket() as connection:
                connection.settimeout(0.2)
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.01)
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        table = pa.Table.from_pylist(
            [{"id": row.id, "name": row.name, "score": row.score} for row in ROWS],
            schema=SCHEMA,
        )
        input_path = plan.output_root / "fixture.parquet"
        pq.write_table(table, input_path)
        if plan.mode == "native_unregistered":
            native_control(spark, receipt, input_path, table)
        else:
            registered_control(spark, receipt, table)
    except BaseException as failure:  # noqa: BLE001 - preserve failed attempts and signals
        receipt.outcome = "timeout" if isinstance(failure, TimeoutError) else "error"
        receipt.errors.append(error("execution", failure))
    finally:
        signal.alarm(0)
        if spark is not None:
            signal.alarm(15)
            try:
                spark.stop()
            except BaseException as failure:  # noqa: BLE001 - cleanup cannot mask query evidence
                receipt.errors.append(error("session_stop", failure))
                receipt.outcome = "error"
            finally:
                signal.alarm(0)
        if server is not None:
            try:
                close_server(server, receipt)
            except BaseException as failure:  # noqa: BLE001 - preserve uncertain closure
                receipt.errors.append(error("server_close", failure))
                receipt.outcome = "error"
        try:
            receipt.identities_after = [pin(value.path) for value in plan.pins]
            if receipt.identities_after != receipt.identities_before:
                raise ValueError("admitted files changed during control")
            receipt.raw_inventory = [
                pin(value)
                for value in sorted(plan.output_root.rglob("*"))
                if value.is_file()
                and value.name not in {"receipt.json", "receipt.json.new"}
            ]
        except BaseException as failure:  # noqa: BLE001 - retain collection failures
            receipt.errors.append(error("identity_closure", failure))
            receipt.outcome = "error"
        receipt.finished_utc = utc()
        save(receipt)
    return 0 if receipt.outcome.startswith("passed_") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    return execute(parser.parse_args().plan)


if __name__ == "__main__":
    raise SystemExit(main())
