"""Fresh local native reservation control; qualification is outside this child."""

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import sysconfig
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import darwin_memory
import probe_models as m
import sail_nutmeg
from pyspark.sql.connect import functions as sf
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from sail_nutmeg.client import Nutmeg


def utc() -> str:
    return datetime.now(UTC).isoformat()


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular file required: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return m.Pin(path=path, bytes=path.stat().st_size, sha256=digest.hexdigest())


def save(path: Path, value: m.Model) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def observe_source(plan: m.Plan) -> dict[str, str]:
    result: dict[str, str] = {}
    for role, repo, source, tree in (
        ("host", plan.repo, plan.source, plan.tree),
        ("extension", plan.extension_repo, plan.extension_source, plan.extension_tree),
    ):
        observed = {}
        for label, arguments in (
            ("head", ["rev-parse", "HEAD"]),
            ("tree", ["rev-parse", "HEAD^{tree}"]),
            ("status", ["status", "--porcelain"]),
        ):
            observed[label] = subprocess.check_output(
                ["git", "-C", str(repo), *arguments], text=True, timeout=10
            ).strip()
        if observed != {"head": source, "tree": tree, "status": ""}:
            raise ValueError(f"{role} HEAD/tree/clean differs")
        result.update({f"{role}_{key}": value for key, value in observed.items()})
    return result


def identities(plan: m.Plan) -> dict[str, m.Pin]:
    expected = [plan.binary, *plan.helpers, *plan.client]
    required = {
        Path(__file__),
        Path(__file__).with_name("probe_models.py"),
        Path(__file__).with_name("darwin_memory.py"),
        Path(sail_nutmeg.__file__).resolve(),
    }
    if (
        Path(m.__file__).resolve()
        != Path(__file__).with_name("probe_models.py").resolve()
    ):
        raise ValueError("actual imported models origin differs")
    if not required.issubset({record.path for record in expected}):
        raise ValueError("actual loaded helper/extension origin must be pinned")
    observed = {record.path.as_posix(): pin(record.path) for record in expected}
    if len(observed) != len(expected) or any(
        observed[record.path.as_posix()] != record for record in expected
    ):
        raise ValueError("source/helper/native-client identity differs")
    return observed


def processes() -> list[m.ProcessRow]:
    result = subprocess.check_output(
        ["ps", "-axo", "pid=,ppid=,pgid=,rss="], text=True, timeout=5
    )
    return [
        m.ProcessRow(pid=int(v[0]), ppid=int(v[1]), pgid=int(v[2]), rss_kib=int(v[3]))
        for line in result.splitlines()
        if len(v := line.split()) == 4
    ]


class Sampler:
    def __init__(self, pgid: int, receipt: m.Receipt) -> None:
        self.pgid = pgid
        self.receipt = receipt
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        try:
            while not self.stop.is_set():
                rows = [
                    row
                    for row in processes()
                    if row.pgid == self.pgid or row.pid == os.getpid()
                ]
                for row in rows:
                    physical = darwin_memory.observe(row.pid)
                    row.resident_size_bytes = physical.resident_size_bytes
                    row.physical_footprint_bytes = physical.physical_footprint_bytes
                    row.process_start_abstime = physical.process_start_abstime
                    row.physical_observation_error = physical.error
                self.receipt.rss_samples.append(
                    m.Sample(
                        observed_utc=utc(),
                        monotonic_seconds=time.monotonic(),
                        processes=rows,
                    )
                )
                self.stop.wait(0.5)
        except Exception as error:  # noqa: BLE001 - retained observer failure
            self.receipt.sampler_error = repr(error)

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            self.receipt.sampler_error = "RSS sampler thread remains alive"


def timed(
    receipt: m.Receipt,
    name: str,
    function: Callable[[], Any],
    *,
    expected_error: bool = False,
) -> Any:
    log = receipt.configuration.output / "server.log"
    action = m.Action(
        name=name,
        started_utc=utc(),
        server_log_start=log.stat().st_size,
        expected_error=expected_error,
        worker_log_start={
            str(path): path.stat().st_size
            for path in sorted(log.parent.glob("worker-*.log"))
        },
    )
    receipt.actions.append(action)
    save(receipt.configuration.output / "receipt.json", receipt)
    started = time.monotonic()
    try:
        value = function()
        action.seconds = time.monotonic() - started
    except Exception as error:
        action.seconds = time.monotonic() - started
        action.error = repr(error)
        if not expected_error:
            raise
        return None
    else:
        if expected_error:
            action.error = "explicit tiny-pool control unexpectedly succeeded"
            raise ValueError(action.error)
        return value
    finally:
        action.finished_utc = utc()
        action.server_log_end = log.stat().st_size
        action.worker_log_end = {
            str(path): path.stat().st_size
            for path in sorted(log.parent.glob("worker-*.log"))
        }
        save(receipt.configuration.output / "receipt.json", receipt)


def quota_events(path: Path) -> list[m.QuotaEvent]:
    return [
        m.QuotaEvent.model_validate_json(line)
        for line in path.read_bytes().splitlines()
        if line
    ]


def actions(spark: SparkSession, receipt: m.Receipt) -> SparkSession:
    plan = receipt.configuration
    audit = plan.output / "native-resource-audit.jsonl"
    endpoint = receipt.endpoint
    if endpoint is None:
        raise ValueError("owned endpoint missing")
    second: SparkSession | None = None
    third: SparkSession | None = None
    receipt.session_ids["first"] = spark.session_id
    first = Nutmeg(spark)

    def stage_cycle() -> None:
        nodes = spark.range(3, numPartitions=4).select(
            sf.col("id").cast("string").alias("node_id")
        )
        edges = spark.range(3, numPartitions=4).select(
            sf.col("id").cast("string").alias("source"),
            ((sf.col("id") + 1) % 3).cast("string").alias("target"),
        )
        first.stage("c3-cycle", nodes, edges, order="asStaged")
        first.run("c3-cycle", "degree").select(
            sf.col("nodeId").cast("string").alias("id"),
            sf.col("degree").cast("long").alias("degree"),
        ).write.mode("error").parquet(str(plan.output / "result"))
        (plan.output / "first-native-status.json").write_text(
            json.dumps(first.status(), indent=2) + "\n"
        )

    try:
        timed(receipt, "first-native-stage-degree-full-parquet", stage_cycle)
        second = SparkSession.builder.remote(endpoint).create()
        second.client.set_retry_policies([DefaultPolicy(max_retries=0)])
        receipt.session_ids["second"] = second.session_id
        rejected_session = second
        timed(
            receipt,
            "second-native-quota-admission-refusal",
            lambda: rejected_session.range(1).collect(),
            expected_error=True,
        )
        second.stop()
        second = None
        before = quota_events(audit)
        admitted = [event for event in before if event.event == "admitted"]
        if len(admitted) != 1 or admitted[0].pid != receipt.server_pid:
            raise ValueError("one driver native lease must precede first session close")
        timed(receipt, "first-session-stop", spark.stop)
        deadline = time.monotonic() + 60
        while not any(
            event.event == "released"
            and event.pid == admitted[0].pid
            and event.id == admitted[0].id
            for event in quota_events(audit)
        ):
            if time.monotonic() >= deadline:
                raise TimeoutError("first native lease did not actually release")
            time.sleep(0.05)
        third = SparkSession.builder.remote(endpoint).create()
        third.client.set_retry_policies([DefaultPolicy(max_retries=0)])
        receipt.session_ids["replacement"] = third.session_id
        replacement_spark = third

        def replacement() -> None:
            if [row.id for row in replacement_spark.range(1).collect()] != [0]:
                raise ValueError("replacement complete range output differs")
            (plan.output / "replacement-native-status.json").write_text(
                json.dumps(Nutmeg(replacement_spark).status(), indent=2) + "\n"
            )

        timed(receipt, "replacement-admission-empty-state", replacement)
        for table, query in metadata_queries().items():
            receipt.evidence_queries[table] = query
            rows = third.sql(query).collect()
            (plan.output / f"system-{table}.json").write_text(
                json.dumps(
                    [row.asDict(recursive=True) for row in rows], default=str, indent=2
                )
                + "\n"
            )
        return third
    except BaseException:
        if second is not None:
            second.stop()
        if third is not None:
            third.stop()
        raise


def metadata_queries() -> dict[str, str]:
    # PySpark4 has no unsigned Arrow integer type. Actual small identifiers are
    # projected to signed64 only in these post-action observation queries.
    # Variant metrics are exported as their JSON representation, not opaque bytes.
    selections = {
        "execution.jobs": "session_id, CAST(job_id AS BIGINT) AS job_id, status, created_at, stopped_at",
        "execution.stages": "session_id, CAST(job_id AS BIGINT) AS job_id, CAST(stage AS BIGINT) AS stage, "
        "CAST(partitions AS BIGINT) AS partitions, CAST(inputs AS ARRAY<STRUCT<stage: BIGINT, mode: STRING>>) AS inputs, "
        "`group`, mode, distribution, placement, status, created_at, stopped_at",
        "execution.tasks": "session_id, CAST(job_id AS BIGINT) AS job_id, CAST(stage AS BIGINT) AS stage, "
        "CAST(partition AS BIGINT) AS partition, CAST(attempt AS BIGINT) AS attempt, status, created_at, stopped_at",
        "cluster.workers": "session_id, CAST(worker_id AS BIGINT) AS worker_id, host, CAST(port AS INT) AS port, "
        "status, created_at, stopped_at",
        "telemetry.metrics": "timestamp, start_timestamp, name, attributes, to_json(value) AS value_json",
    }
    return {
        table: f"SELECT {columns} FROM system.{table}"
        for table, columns in selections.items()
    }


def environment(plan: m.Plan) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SAIL_", "NUTMEG_", "TOKIO_", "RAYON_"))
    }
    env.update(
        PYTHONHOME=sys.base_prefix,
        PYTHONPATH=sysconfig.get_paths()["purelib"],
        PYTHONDONTWRITEBYTECODE="1",
        DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "",
        SAIL_MODE="local",
        SAIL_EXPERIMENTAL_EXTENSIONS="1",
        NUTMEG_WORKERS="16",
        SAIL_GRAPH_UTILS_ROOT=(plan.output / "staging").as_uri(),
        SAIL_EXECUTION__DEFAULT_PARALLELISM="16",
        SAIL_EXECUTION__CHECKPOINT__PATH=(plan.output / "checkpoint").as_uri(),
        SAIL_RUNTIME__MEMORY_POOL__TYPE="greedy",
        SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(plan.pool_bytes_per_process),
        SAIL_NUTMEG_MEMORY_BYTES=str(plan.native_quota_bytes),
        NUTMEG_MEMORY_BYTES=str(plan.native_quota_bytes),
        SAIL_NATIVE_RESOURCE_AUDIT=str(plan.output / "native-resource-audit.jsonl"),
        TOKIO_WORKER_THREADS="16",
        RAYON_NUM_THREADS="16",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        RUST_LOG="info,sail_execution=debug",
    )
    return env


def expired(_signum: int, _frame: Any) -> None:
    raise TimeoutError("native probe deadline elapsed")


def execute(path: Path) -> int:
    plan = m.Plan.model_validate_json(path.read_bytes())
    plan.output.mkdir(parents=True, exist_ok=False)
    receipt = m.Receipt(
        configuration=plan,
        configuration_pin=pin(path),
        started_utc=utc(),
        owner_pid=os.getpid(),
    )
    process: subprocess.Popen[str] | None = None
    sampler: Sampler | None = None
    spark: SparkSession | None = None
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(plan.timeout_seconds)
    try:
        receipt.inputs_before = identities(plan)
        receipt.source_before = observe_source(plan)
        (plan.output / "staging").mkdir(exist_ok=False)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        admitted_env = environment(plan)
        env_path = plan.output / "admitted-environment.json"
        env_path.write_text(
            json.dumps(
                {
                    key: value
                    for key, value in admitted_env.items()
                    if key.startswith(("SAIL_", "NUTMEG_"))
                    or key
                    in {
                        "TOKIO_WORKER_THREADS",
                        "RAYON_NUM_THREADS",
                        "OMP_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS",
                    }
                },
                indent=2,
            )
            + "\n"
        )
        receipt.admitted_environment = pin(env_path)
        with (plan.output / "server.log").open("x") as log:
            process = subprocess.Popen(
                [
                    str(plan.binary.path),
                    "spark",
                    "server",
                    "--ip",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=admitted_env,
                cwd=plan.output,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        receipt.server_pid = process.pid
        save(plan.output / "receipt.json", receipt)
        sampler = Sampler(process.pid, receipt)
        sampler.thread.start()
        deadline = time.monotonic() + 120
        while True:
            if process.poll() is not None:
                raise RuntimeError("native server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("native server startup deadline")
                time.sleep(0.05)
        receipt.endpoint = f"sc://127.0.0.1:{port}"
        spark = SparkSession.builder.remote(receipt.endpoint).create()
        spark.client.set_retry_policies([DefaultPolicy(max_retries=0)])
        # The local client create() is lazy. This metadata-only AnalyzePlan
        # creates the actual session and activates its initial workers.
        started_utc, started = utc(), time.monotonic()
        bootstrap_log_start = (plan.output / "server.log").stat().st_size
        spark_version = spark.version
        receipt.session_bootstrap = m.SessionBootstrap(
            started_utc=started_utc,
            finished_utc=utc(),
            seconds=time.monotonic() - started,
            spark_version=spark_version,
            server_log_start=bootstrap_log_start,
            server_log_end=(plan.output / "server.log").stat().st_size,
        )
        save(plan.output / "receipt.json", receipt)
        spark = actions(spark, receipt)
    except BaseException as error:  # noqa: BLE001 - retain cancellation and owned cleanup
        receipt.errors.append(f"{error!r}: {error}")
        receipt.traceback = traceback.format_exc()
    finally:
        signal.alarm(90)
        if spark is not None:
            try:
                spark.stop()
            except Exception as error:  # noqa: BLE001 - cleanup failure remains unqualified
                receipt.errors.append(f"spark.stop: {error!r}")
        if process is not None:
            try:
                if process.poll() is None:
                    receipt.shutdown_sigint = True
                    os.killpg(process.pid, signal.SIGINT)
                else:
                    receipt.errors.append("native server exited before owned shutdown")
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    receipt.shutdown_sigkill = True
                    receipt.errors.append("native server required SIGKILL")
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                deadline = time.monotonic() + 10
                while (
                    any(row.pgid == process.pid for row in processes())
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                remaining = [row for row in processes() if row.pgid == process.pid]
                if remaining:
                    receipt.errors.append(
                        "owned group persisted after ordinary shutdown"
                    )
                receipt.server_returncode = process.returncode
                receipt.server_wait_completed = True
                if process.returncode not in (0, -signal.SIGINT):
                    receipt.errors.append(
                        f"unexpected native server returncode: {process.returncode}"
                    )
                receipt.server_group_absent = not any(
                    row.pgid == process.pid for row in processes()
                )
            except Exception as error:  # noqa: BLE001 - owned cleanup must never qualify failure
                receipt.errors.append(f"server cleanup: {error!r}")
        if sampler is not None:
            sampler.close()
        try:
            workers = [
                json.loads(p.read_bytes())
                for p in sorted(plan.output.glob("worker-*.json"))
            ]
            receipt.worker_pids = [int(worker["pid"]) for worker in workers]
            current = processes()
            receipt.worker_groups_absent = not any(
                row.pid in receipt.worker_pids
                or row.pgid in {int(w["pgid"]) for w in workers}
                for row in current
            )
            receipt.inputs_after = identities(plan)
            receipt.source_after = observe_source(plan)
            if (
                len(workers) != 0
                or receipt.inputs_before != receipt.inputs_after
                or receipt.source_before != receipt.source_after
            ):
                raise ValueError("local worker inventory or final identities differ")
        except Exception as error:  # noqa: BLE001 - final evidence failure is retained
            receipt.errors.append(f"final evidence: {error!r}")
        if (
            not receipt.server_group_absent
            or not receipt.worker_groups_absent
            or receipt.sampler_error
            or receipt.shutdown_sigkill
        ):
            receipt.errors.append("closure or RSS observation incomplete")
        audit = plan.output / "native-resource-audit.jsonl"
        if audit.is_file():
            receipt.native_audit = pin(audit)
        else:
            receipt.errors.append("native resource audit missing")
        receipt.finished_utc = utc()
        receipt.outcome = "error" if receipt.errors else "completed_unqualified"
        save(plan.output / "receipt.json", receipt)
        signal.alarm(0)
    return 0 if receipt.outcome == "completed_unqualified" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.plan))


if __name__ == "__main__":
    main()
