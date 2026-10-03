"""Sequential materialized Arrow-client profile; algorithm includes result transport."""

import argparse
import hashlib
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import FrameType
from typing import Literal, TypeVar

import pyarrow as pa
import pyarrow.parquet as pq
import pyspark
from pydantic import JsonValue, TypeAdapter
from pyspark.sql.connect import functions as F
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.plan import CachedRemoteRelation, LocalRelation
from pyspark.sql.connect.session import SparkSession
from sail_nutmeg.client import Nutmeg

from f2a_models import (
    ArrowHandoff,
    Error,
    FilePin,
    NativeStatus,
    OutputAttempt,
    Phase,
    Plan,
    Receipt,
    ServerExit,
    Span,
)

T = TypeVar("T")
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def utc() -> str:
    return datetime.now(UTC).isoformat()


def pin(path: Path) -> FilePin:
    raw = path.read_bytes()
    return FilePin(
        path=path.resolve(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )


def module_pin(name: str) -> FilePin:
    path = sys.modules[name].__file__
    if path is None:
        raise ValueError(f"client module has no physical source: {name}")
    return pin(Path(path))


def save(receipt: Receipt) -> None:
    receipt.observed_utc = utc()
    path = receipt.configuration.receipt
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        file.write(receipt.model_dump_json(indent=2) + "\n")
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def interrupted(number: int, _frame: FrameType | None) -> None:
    if number == signal.SIGALRM:
        raise TimeoutError("native worker's execution or cleanup budget expired")
    raise InterruptedError(f"native worker interrupted by signal {number}")


def environment(plan: Plan) -> dict[str, str]:
    return {
        "PYTHONHOME": str(plan.python_home),
        "PYTHONPATH": str(plan.python_purelib),
        "DYLD_LIBRARY_PATH": str(plan.python_library_directory),
        "SAIL_EXPERIMENTAL_EXTENSIONS": "1",
        "SAIL_MODE": "local",
        "SAIL_EXECUTION__DEFAULT_PARALLELISM": str(plan.workers),
        "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
        "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(plan.sail_pool_bytes),
        "SAIL_NUTMEG_MEMORY_BYTES": str(plan.native_quota_bytes),
        "NUTMEG_MEMORY_BYTES": str(plan.native_quota_bytes),
        "NUTMEG_WORKERS": str(plan.workers),
        "SAIL_GRAPH_UTILS_ROOT": (plan.output_root / "staging").as_uri(),
        "TOKIO_WORKER_THREADS": str(plan.workers),
        "RAYON_NUM_THREADS": str(plan.workers),
        "TMPDIR": str(plan.output_root / "temporary"),
        "RUST_LOG": "warn",
    }


def timed(
    receipt: Receipt,
    name: Literal[
        "read_parquet", "csr_and_graph", "algorithm_materialize", "write_parquet"
    ],
    action: Callable[[], T],
    call: int | None = None,
) -> T:
    started = time.perf_counter_ns()
    completed = False
    try:
        value = action()
        completed = True
        return value
    finally:
        receipt.phases.append(
            Phase(
                name=name,
                call=call,
                completed=completed,
                span=Span(started_ns=started, ended_ns=time.perf_counter_ns()),
            )
        )


def materialized_read(plan: Plan) -> tuple[pa.Table, pa.Table]:
    nodes = pq.read_table(
        plan.vertices, columns=[plan.vertex_id_column]
    ).rename_columns(["node_id"])
    edges = pq.read_table(
        plan.edges, columns=[plan.edge_source_column, plan.edge_target_column]
    ).rename_columns(["source", "target"])
    return nodes, edges


def cached_chunk(frame: DataFrame) -> bool:
    """Source-pinned 4.0.1 checkpoint result: a remote relation reference."""
    node = frame._plan
    for _depth in range(32):
        if node is None or isinstance(node, LocalRelation):
            return False
        if isinstance(node, CachedRemoteRelation):
            return True
        node = node._child
    return False


def inline_chunk(frame: DataFrame) -> bool:
    """Each bounded createDataFrame must be inline and bypass artifact-cache RPCs."""
    node = frame._plan
    for _depth in range(32):
        if node is None or isinstance(node, CachedRemoteRelation):
            return False
        if isinstance(node, LocalRelation):
            return True
        node = node._child
    return False


def bounded_handoff(
    spark: SparkSession,
    table: pa.Table,
    receipt: Receipt,
    name: Literal["vertices", "edges"],
) -> DataFrame:
    frames: list[DataFrame] = []
    handoff = ArrowHandoff(
        input_name=name,
        rows=table.num_rows,
        chunk_rows=receipt.configuration.chunk_rows,
        chunks=max(
            1,
            (table.num_rows + receipt.configuration.chunk_rows - 1)
            // receipt.configuration.chunk_rows,
        ),
        cached_chunks=0,
        maximum_ipc_bytes=0,
        encoded_ipc_bytes=0,
        balanced_union_depth=0,
    )
    receipt.arrow_handoffs.append(handoff)
    maximum = total_bytes = 0
    for offset in range(0, max(table.num_rows, 1), receipt.configuration.chunk_rows):
        chunk = table.slice(offset, receipt.configuration.chunk_rows)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, chunk.schema) as writer:
            for batch in chunk.to_batches():
                writer.write_batch(batch)
        size = sink.getvalue().size
        if size > 32 * 1024 * 1024:
            raise ValueError("Arrow slice exceeds the admitted 32MiB IPC bound")
        maximum, total_bytes = max(maximum, size), total_bytes + size
        handoff.checked_ipc_encodings += 1
        handoff.maximum_ipc_bytes = maximum
        handoff.encoded_ipc_bytes = total_bytes
        del sink
        handoff.create_dataframe_calls += 1
        frame = spark.createDataFrame(chunk)
        if not inline_chunk(frame):
            raise ValueError(
                "bounded Arrow slice did not remain an inline LocalRelation"
            )
        handoff.checkpoint_attempts += 1
        frame = frame.checkpoint(eager=True)
        handoff.checkpoints_completed += 1
        if not cached_chunk(frame):
            raise ValueError(
                "checkpoint did not return a CachedRemoteRelation reference"
            )
        reference = getattr(frame._plan, "_relation_id", None)
        if not isinstance(reference, str) or not reference:
            raise ValueError("checkpoint lacks its actual remote relation reference id")
        handoff.remote_reference_ids.append(reference)
        handoff.cached_chunks += 1
        frames.append(frame)
    chunks = len(frames)
    if chunks != handoff.chunks:
        raise ValueError("actual Arrow chunk count differs from the declared bound")
    depth = 0
    while len(frames) > 1:
        frames = [
            frames[index].unionByName(frames[index + 1])
            if index + 1 < len(frames)
            else frames[index]
            for index in range(0, len(frames), 2)
        ]
        depth += 1
    handoff.balanced_union_depth = depth
    handoff.completed = True
    return frames[0]


def materialized_csr(
    spark: SparkSession,
    nutmeg: Nutmeg,
    tables: tuple[pa.Table, pa.Table],
    receipt: Receipt,
) -> tuple[JsonValue, JsonValue]:
    # Inline one bounded slice, checkpoint it, then union only remote references.
    # ArtifactStatus is unsupported on this runtime; never request that cache API.
    spark.conf.set("spark.sql.session.localRelationCacheThreshold", "67108864")
    if spark.conf.get("spark.sql.session.localRelationCacheThreshold") != "67108864":
        raise ValueError(
            "client/server did not admit the explicit relation-cache threshold"
        )
    nodes = bounded_handoff(spark, tables[0], receipt, "vertices")
    edges = bounded_handoff(spark, tables[1], receipt, "edges")
    stage = nutmeg.stage(
        "g",
        nodes,
        edges,
        node_mapping={"ids": "int64"},
        edge_mapping={"ids": "int64"},
        order="asStaged",
    )
    stats = nutmeg.run("g", "projectionStats").first()
    if stats is None:
        raise ValueError("projectionStats returned no row")
    return JSON.validate_python(
        stage.asDict(recursive=True), strict=True
    ), JSON.validate_python(stats.asDict(recursive=True), strict=True)


def materialized_algorithms(nutmeg: Nutmeg, plan: Plan) -> list[pa.Table]:
    results = []
    for _call in range(plan.calls):
        frame = nutmeg.run("g", "wcc", concurrency=plan.workers).select(
            F.col("nodeId").cast("long").alias("id"),
            F.col("componentId").cast("long").alias("component"),
        )
        table, _schema = frame._to_table()
        results.append(table)
    return results


def materialized_write(tables: list[pa.Table], receipt: Receipt) -> None:
    for call, table in enumerate(tables, 1):
        path = receipt.configuration.output_root / f"result-call{call}"
        attempt = OutputAttempt(call=call, path=path)
        receipt.outputs.append(attempt)
        path.mkdir(exist_ok=False)
        pq.write_table(table, path / "part-0.parquet")
        attempt.completed = True


def pipeline(spark: SparkSession, nutmeg: Nutmeg, receipt: Receipt) -> None:
    plan = receipt.configuration
    if plan.ids != "int64":
        raise ValueError("materialized profile requires the integer-ID contract")
    pa.set_cpu_count(plan.workers)
    started = time.perf_counter_ns()
    try:
        tables = timed(receipt, "read_parquet", partial(materialized_read, plan))
        receipt.stage_receipt, receipt.projection_receipt = timed(
            receipt,
            "csr_and_graph",
            partial(materialized_csr, spark, nutmeg, tables, receipt),
        )
        del tables
        results = timed(
            receipt,
            "algorithm_materialize",
            partial(materialized_algorithms, nutmeg, plan),
        )
        timed(receipt, "write_parquet", partial(materialized_write, results, receipt))
        receipt.pipeline_completed = True
        receipt.exclusive_sem_phases.read_seconds = receipt.phases[0].span.seconds
        receipt.exclusive_sem_phases.csr_and_graph_build_seconds = receipt.phases[
            1
        ].span.seconds
        receipt.exclusive_sem_phases.algorithm_seconds = receipt.phases[2].span.seconds
        receipt.exclusive_sem_phases.write_seconds = receipt.phases[3].span.seconds
        receipt.exclusive_sem_phases.availability = "observed_materialized_arrow_bridge"
    finally:
        ended = (
            receipt.phases[-1].span.ended_ns
            if receipt.pipeline_completed
            else time.perf_counter_ns()
        )
        receipt.pipeline = Span(started_ns=started, ended_ns=ended)
        receipt.pipeline_seconds = receipt.pipeline.seconds


def ready(server: subprocess.Popen[bytes], port: int) -> None:
    while True:
        if server.poll() is not None:
            raise RuntimeError(
                f"native server exited before readiness: rc={server.returncode}"
            )
        with socket.socket() as connection:
            connection.settimeout(0.2)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.01)


def close_server(server: subprocess.Popen[bytes], receipt: Receipt) -> None:
    proof = receipt.server
    if proof is None:
        if server.poll() is None:
            server.terminate()
        try:
            server.wait(timeout=120)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=30)
        raise RuntimeError("native process lacks its launch record")
    if server.poll() is None:
        proof.termination_requested = True
        server.terminate()
    try:
        proof.returncode = server.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proof.forced_kill = True
        server.kill()
        proof.returncode = server.wait(timeout=30)
        raise RuntimeError(
            "native server required forced kill after graceful wait expired"
        ) from None
    finally:
        proof.closed_utc = utc()
        proof.wait_completed = server.returncode is not None
    if not proof.termination_requested and proof.returncode != 0:
        raise RuntimeError(f"native server exited unexpectedly: rc={proof.returncode}")


def record_error(receipt: Receipt, phase: str) -> None:
    receipt.errors.append(Error(phase=phase, detail=traceback.format_exc()))
    if receipt.outcome != "timeout":
        receipt.outcome = "failed"


def execute(plan_file: Path) -> int:
    plan_pin = pin(plan_file)
    plan = Plan.model_validate_json(plan_file.read_bytes())
    if sys.version_info[:3] != (3, 12, 6):
        raise ValueError("worker interpreter must be the admitted Python 3.12.6 venv")
    if Path(sys.prefix).resolve() != plan.venv.resolve():
        raise ValueError("worker interpreter does not belong to the declared venv")
    plan.output_root.mkdir(parents=True, exist_ok=False)
    (plan.output_root / "staging").mkdir()
    (plan.output_root / "temporary").mkdir()
    plan.receipt.parent.mkdir(parents=True, exist_ok=True)
    with plan.receipt.open("x"):
        pass
    receipt = Receipt(
        observed_utc=utc(),
        started_utc=utc(),
        outcome="running",
        configuration=plan,
        configuration_pin=plan_pin,
        worker_source=pin(Path(__file__)),
        models_source=pin(Path(__file__).with_name("f2a_models.py")),
        owner_pid=os.getpid(),
        python_version=sys.version,
        pyspark_version=pyspark.__version__,
        client_plan_source=module_pin(CachedRemoteRelation.__module__),
        client_session_source=module_pin(SparkSession.__module__),
        client_dataframe_source=module_pin(DataFrame.__module__),
        python_executable=Path(sys.executable),
        environment=environment(plan),
    )
    save(receipt)
    server: subprocess.Popen[bytes] | None = None
    spark: SparkSession | None = None
    nutmeg: Nutmeg | None = None
    for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    signal.alarm(plan.timeout_seconds)
    try:
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
            launched = utc()
            server = subprocess.Popen(
                argv,
                env=inherited,
                cwd=plan.output_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            receipt.server = ServerExit(
                pid=server.pid, pgid=server.pid, argv=argv, launched_utc=launched
            )
            receipt.server.pgid = os.getpgid(server.pid)
            if receipt.server.pgid != server.pid:
                raise RuntimeError(
                    "owned server did not start in its declared fresh process group"
                )
            save(receipt)
        ready(server, port)
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        nutmeg = Nutmeg(spark)
        pipeline(spark, nutmeg, receipt)
        receipt.native_status = JSON.validate_python(nutmeg.status(), strict=True)
        status = NativeStatus.model_validate(receipt.native_status)
        receipt.projection_reused = status.one_cached_projection()
        if not receipt.projection_reused:
            raise ValueError(
                "expected exactly one cached projection build for this WCC series"
            )
        receipt.outcome = "completed_unvalidated"
    except TimeoutError:
        receipt.outcome = "timeout"
        record_error(receipt, "execution")
    except BaseException:  # noqa: BLE001 - preserve interrupts and all failed attempts
        record_error(receipt, "execution")
    finally:
        signal.alarm(0)
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, signal.SIG_IGN)
        if nutmeg is not None:
            try:
                signal.alarm(30)
                nutmeg.drop("g")
                receipt.graph_dropped = True
            except BaseException:  # noqa: BLE001 - retain cleanup failure and continue wait
                record_error(receipt, "graph_drop")
            finally:
                signal.alarm(0)
        if spark is not None:
            try:
                signal.alarm(30)
                spark.stop()
                receipt.spark_stopped = True
            except BaseException:  # noqa: BLE001 - retain cleanup failure and continue wait
                record_error(receipt, "spark_stop")
            finally:
                signal.alarm(0)
        if server is not None:
            try:
                close_server(server, receipt)
            except BaseException:  # noqa: BLE001 - retain actual native exit and wait failure
                record_error(receipt, "native_server_wait")
        try:
            if pin(plan_file) != plan_pin:
                raise ValueError("approved plan changed during run")
            if (
                pin(Path(__file__)) != receipt.worker_source
                or pin(Path(__file__).with_name("f2a_models.py"))
                != receipt.models_source
            ):
                raise ValueError("worker source changed during run")
        except BaseException:  # noqa: BLE001 - preserve final source/configuration failure
            record_error(receipt, "source_and_configuration")
        save(receipt)
    print(receipt.model_dump_json(), flush=True)
    return 0 if receipt.outcome == "completed_unvalidated" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(execute(args.plan.resolve()))


if __name__ == "__main__":
    main()
