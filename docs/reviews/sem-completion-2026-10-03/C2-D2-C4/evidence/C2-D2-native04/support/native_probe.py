"""Fresh native two-worker C2/D2 actions. Full qualification is outside this child."""
import argparse
import functools
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
import worker_ready
from pyspark.sql.connect import functions as sf
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.session import SparkSession


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
    result = {}
    for label, arguments in (("head", ["rev-parse", "HEAD"]),
                             ("tree", ["rev-parse", "HEAD^{tree}"]),
                             ("status", ["status", "--porcelain"])):
        result[label] = subprocess.check_output(
            ["git", "-C", str(plan.repo), *arguments], text=True, timeout=10).strip()
    if result != {"head": plan.source, "tree": plan.tree, "status": ""}:
        raise ValueError("source HEAD/tree/clean differs")
    return result


def identities(plan: m.Plan) -> dict[str, m.Pin]:
    if plan.fixture_manifest.path != plan.fixture / "manifest.json":
        raise ValueError("fixture manifest path differs")
    manifest = m.FixtureManifest.model_validate_json(plan.fixture_manifest.path.read_bytes())
    names = {"vertices.parquet", "reference.json", *(f"edges/part-{i:02}.parquet" for i in range(8))}
    if set(manifest.files) != names or {p.path for p in plan.originals} != {plan.fixture / name for name in names}:
        raise ValueError("complete original fixture pin set required")
    if any(m.Identity(bytes=p.bytes, sha256=p.sha256) != manifest.files[p.path.relative_to(plan.fixture).as_posix()]
           for p in plan.originals):
        raise ValueError("fixture manifest and original pins differ")
    expected = [plan.binary, plan.fixture_manifest, *plan.originals, *plan.helpers, *plan.client]
    required = {Path(__file__), Path(__file__).with_name("probe_models.py"),
                Path(__file__).with_name("worker_exec.py"), Path(__file__).with_name("darwin_memory.py"),
                Path(__file__).with_name("worker_ready.py")}
    if Path(m.__file__).resolve() != Path(__file__).with_name("probe_models.py").resolve():
        raise ValueError("actual imported models origin differs")
    if not required.issubset({p.path for p in plan.helpers}):
        raise ValueError("loaded worker/models/exec wrapper must be pinned helpers")
    observed = {p.path.as_posix(): pin(p.path) for p in expected}
    if len(observed) != len(expected) or any(observed[p.path.as_posix()] != p for p in expected):
        raise ValueError("source/helper/input/client identity differs")
    return observed


def processes() -> list[m.ProcessRow]:
    result = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pgid=,rss="], text=True, timeout=5)
    return [m.ProcessRow(pid=int(v[0]), ppid=int(v[1]), pgid=int(v[2]), rss_kib=int(v[3]))
            for line in result.splitlines() if len(v := line.split()) == 4]


class Sampler:
    def __init__(self, pgid: int, receipt: m.Receipt) -> None:
        self.pgid = pgid
        self.receipt = receipt
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        try:
            while not self.stop.is_set():
                rows = [row for row in processes() if row.pgid == self.pgid or row.pid == os.getpid()]
                for row in rows:
                    physical = darwin_memory.observe(row.pid)
                    row.resident_size_bytes = physical.resident_size_bytes
                    row.physical_footprint_bytes = physical.physical_footprint_bytes
                    row.process_start_abstime = physical.process_start_abstime
                    row.physical_observation_error = physical.error
                self.receipt.rss_samples.append(m.Sample(observed_utc=utc(),
                    monotonic_seconds=time.monotonic(), processes=rows))
                self.stop.wait(0.5)
        except Exception as error:  # noqa: BLE001 - retained observer failure
            self.receipt.sampler_error = repr(error)

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            self.receipt.sampler_error = "RSS sampler thread remains alive"


def timed(receipt: m.Receipt, name: str, function: Callable[[], Any],
          *, expected_error: bool = False) -> Any:
    log = receipt.configuration.output / "server.log"
    action = m.Action(name=name, started_utc=utc(), server_log_start=log.stat().st_size,
                      expected_error=expected_error)
    receipt.actions.append(action)
    save(receipt.configuration.output / "receipt.json", receipt)
    started = time.monotonic()
    try:
        value = function()
        action.seconds = time.monotonic() - started
        if expected_error:
            raise ValueError("expected sentinel error was not raised")
        return value
    except Exception as error:
        action.seconds = time.monotonic() - started
        action.error = repr(error)
        if not expected_error or "sem-stream-diagnostic-sentinel" not in str(error):
            raise
        return None
    finally:
        action.finished_utc = utc()
        action.server_log_end = log.stat().st_size
        save(receipt.configuration.output / "receipt.json", receipt)


def collect(receipt: m.Receipt, name: str, frame: DataFrame) -> None:
    schema = [(field.name, field.dataType.simpleString()) for field in frame.schema]
    rows = timed(receipt, name, frame.collect)
    normalized = []
    for row in rows:
        values = list(row)
        if any(type(value) is not int for value in values):
            raise ValueError("probe raw output contains non-BIGINT values")
        normalized.append(values)
    receipt.actions[-1].raw_rows = sorted(normalized)
    receipt.actions[-1].raw_schema = schema
    save(receipt.configuration.output / "receipt.json", receipt)


def actions(spark: SparkSession, receipt: m.Receipt) -> None:
    plan = receipt.configuration
    edges = spark.read.parquet(str(plan.fixture / "edges"))
    if plan.kind == "c2":
        result = edges.repartition(plan.partitions, "src").groupBy("src").agg(
            sf.min("payload").alias("minimum"), sf.count("*").alias("count"))
        collect(receipt, "cold-first-data-action", result)
        collect(receipt, "warm-same-query-same-server", result)
    elif plan.kind == "d2":
        vertices = spark.read.parquet(str(plan.fixture / "vertices.parquet"))
        plain = plan.output / "plain-state"
        timed(receipt, "state-plain-write-setup", lambda: vertices.write.mode("error").parquet(str(plain)))
        path_state = spark.read.parquet(str(plain))
        keyed_edges = timed(receipt, "edges-keyed-checkpoint-setup", lambda:
            edges.repartition(plan.partitions, "src").checkpoint())
        keyed_state = timed(receipt, "state-keyed-checkpoint-setup", lambda:
            path_state.repartition(plan.partitions, "id").checkpoint())
        for repetition in range(plan.repetitions):
            for label, state, adjacency in (("path-path", path_state, edges),
                                            ("checkpoint-path", keyed_state, edges),
                                            ("checkpoint-checkpoint", keyed_state, keyed_edges)):
                messages = state.join(adjacency, state.id == adjacency.src).groupBy("dst").agg(
                    sf.sum("val").alias("total"), sf.count("*").alias("count"))
                collect(receipt, f"round-{label}-{repetition:02}", messages)
            for label, frame in (("read-state-path", path_state), ("read-state-checkpoint", keyed_state),
                                 ("read-edges-path", edges), ("read-edges-checkpoint", keyed_edges)):
                collect(receipt, f"{label}-{repetition:02}", frame)
            timed(receipt, f"state-plain-write-{repetition:02}", functools.partial(
                path_state.write.mode("error").parquet, str(plan.output / f"state-write-{repetition:02}")))
            timed(receipt, f"state-keyed-checkpoint-{repetition:02}", lambda:
                path_state.repartition(plan.partitions, "id").checkpoint())
    else:
        good = spark.range(0, 128, 1, 8).repartition(plan.partitions, "id").groupBy(
            (sf.col("id") % 2).alias("key")).agg(sf.sum("id").alias("total"), sf.count("*").alias("count"))
        timed(receipt, "stream-success-parquet", lambda: good.write.mode("error").parquet(str(plan.output / "result")))
        bad = spark.sql("SELECT raise_error(concat('sem-stream-diagnostic-sentinel', ':', "
                        "cast(count(*) AS STRING))) FROM range(0,128,1,2) GROUP BY id % 2")
        timed(receipt, "stream-typed-sentinel", bad.collect, expected_error=True)
    # These evidence queries are after all measured data actions. Their own jobs are not workload jobs.
    for table, query in metadata_queries().items():
        receipt.evidence_queries[table] = query
        save(plan.output / "receipt.json", receipt)
        rows = spark.sql(query).collect()
        (plan.output / f"system-{table}.json").write_text(json.dumps(
            [row.asDict(recursive=True) for row in rows], default=str, indent=2) + "\n")


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
    return {table: f"SELECT {columns} FROM system.{table}" for table, columns in selections.items()}


def environment(plan: m.Plan) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SAIL_", "NUTMEG_"))}
    env.update(PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
        PYTHONDONTWRITEBYTECODE="1",
        DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local-cluster",
        SAIL_EXPERIMENTAL_PROCESS_WORKERS="1", SAIL_CLUSTER__WORKER_INITIAL_COUNT="2",
        SAIL_CLUSTER__WORKER_MAX_COUNT="2", SAIL_CLUSTER__WORKER_TASK_SLOTS=str(plan.worker_task_slots),
        SAIL_CLUSTER__TASK_MAX_ATTEMPTS="1", SAIL_EXECUTION__DEFAULT_PARALLELISM=str(plan.partitions),
        SAIL_EXECUTION__CHECKPOINT__PATH=(plan.output / "checkpoint").as_uri(),
        SAIL_RUNTIME__MEMORY_POOL__TYPE="greedy", SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(plan.pool_bytes_per_process),
        SAIL_TELEMETRY__EXPORT_METRICS="true", SAIL_TELEMETRY__EXPORTER__SYSTEM__ENABLED="true",
        SAIL_TELEMETRY__METRICS_COLLECTION_INTERVAL_SECS="1", SAIL_TELEMETRY__METRICS_EXPORT_INTERVAL_SECS="1",
        TOKIO_WORKER_THREADS="16", RAYON_NUM_THREADS="16", OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", RUST_LOG="info,sail_execution=debug")
    env["SAIL_EXPERIMENTAL_WORKER_COMMAND"] = json.dumps([
        sys.executable, "-I", "-B", str(Path(__file__).with_name("worker_exec.py")),
        "--binary", str(plan.binary.path), "--output", str(plan.output)])
    return env


def await_workers(process: subprocess.Popen[str], receipt: m.Receipt) -> None:
    plan = receipt.configuration
    started_utc, started = utc(), time.monotonic()
    deadline = started + 30
    log = plan.output / "server.log"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("native server exited before worker readiness")
        raw = log.read_bytes()
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("startup log exceeds bounded readiness inventory")
        ids = worker_ready.registered_ids(raw.decode())
        records = [json.loads(path.read_bytes()) for path in sorted(plan.output.glob("worker-*.json"))]
        if len(records) == 2 and ids == {int(record["worker_id"]) for record in records}:
            if any(int(record["pgid"]) != process.pid or record["argv"] != [str(plan.binary.path), "worker"]
                   for record in records):
                raise ValueError("ready workers do not bind actual owned group/binary")
            receipt.worker_readiness = m.WorkerReadiness(started_utc=started_utc, finished_utc=utc(),
                seconds=time.monotonic() - started, server_log_end=len(raw), worker_ids=sorted(ids),
                worker_pids=sorted(int(record["pid"]) for record in records),
                identity_files=[pin(path) for path in sorted(plan.output.glob("worker-*.json"))])
            save(plan.output / "receipt.json", receipt)
            return
        time.sleep(0.05)
    raise TimeoutError("both native worker registrations were not observed before first data action")


def expired(_signum: int, _frame: Any) -> None:
    raise TimeoutError("native probe deadline elapsed")


def execute(path: Path) -> int:
    plan = m.Plan.model_validate_json(path.read_bytes())
    plan.output.mkdir(parents=True, exist_ok=False)
    receipt = m.Receipt(configuration=plan, configuration_pin=pin(path), started_utc=utc(), owner_pid=os.getpid())
    process: subprocess.Popen[str] | None = None
    sampler: Sampler | None = None
    spark: SparkSession | None = None
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(plan.timeout_seconds)
    try:
        receipt.inputs_before = identities(plan)
        receipt.source_before = observe_source(plan)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (plan.output / "server.log").open("x") as log:
            process = subprocess.Popen([str(plan.binary.path), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                env=environment(plan), cwd=plan.output, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, text=True)
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
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        # The local client create() is lazy. This metadata-only AnalyzePlan
        # creates the actual session and activates its initial workers.
        started_utc, started = utc(), time.monotonic()
        bootstrap_log_start = (plan.output / "server.log").stat().st_size
        spark_version = spark.version
        receipt.session_bootstrap = m.SessionBootstrap(started_utc=started_utc, finished_utc=utc(),
            seconds=time.monotonic() - started, spark_version=spark_version,
            server_log_start=bootstrap_log_start, server_log_end=(plan.output / "server.log").stat().st_size)
        save(plan.output / "receipt.json", receipt)
        await_workers(process, receipt)
        actions(spark, receipt)
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
                while any(row.pgid == process.pid for row in processes()) and time.monotonic() < deadline:
                    time.sleep(0.05)
                remaining = [row for row in processes() if row.pgid == process.pid]
                if remaining:
                    receipt.errors.append("owned group persisted after ordinary shutdown")
                receipt.server_returncode = process.returncode
                receipt.server_wait_completed = True
                if process.returncode not in (0, -signal.SIGINT):
                    receipt.errors.append(f"unexpected native server returncode: {process.returncode}")
                receipt.server_group_absent = not any(row.pgid == process.pid for row in processes())
            except Exception as error:  # noqa: BLE001 - owned cleanup must never qualify failure
                receipt.errors.append(f"server cleanup: {error!r}")
        if sampler is not None:
            sampler.close()
        try:
            workers = [json.loads(p.read_bytes()) for p in sorted(plan.output.glob("worker-*.json"))]
            receipt.worker_pids = [int(worker["pid"]) for worker in workers]
            current = processes()
            receipt.worker_groups_absent = bool(workers) and not any(
                row.pid in receipt.worker_pids or row.pgid in {int(w["pgid"]) for w in workers} for row in current)
            receipt.inputs_after = identities(plan)
            receipt.source_after = observe_source(plan)
            if len(workers) != 2 or receipt.inputs_before != receipt.inputs_after or receipt.source_before != receipt.source_after:
                raise ValueError("workers or final identities differ")
        except Exception as error:  # noqa: BLE001 - final evidence failure is retained
            receipt.errors.append(f"final evidence: {error!r}")
        if not receipt.server_group_absent or not receipt.worker_groups_absent or receipt.sampler_error or receipt.shutdown_sigkill:
            receipt.errors.append("closure or RSS observation incomplete")
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
