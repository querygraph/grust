"""A2/A3 engine-only child; the supervisor owns hashes, admission and oracles.

Time this process from launch through exit. Owned input snapshots remain inside
that boundary (B7 is not applied). BFS exports raw id/distance only; the public
frontier method also computes parent/hops internally. No data audit or oracle
runs here, and no distance casts or unreachable-value normalization are added.
Bootstrap supplies f3b Pecan, frozen 6ae benchmark helpers and dependency paths.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys
import time
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Literal, cast

import measurement
import runtime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyspark.sql import DataFrame
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import algorithms
from pyspark_pecan.lifecycle import GraphResult
from pyspark_pecan.staging import StagingRun
from pyspark_pecan.types import IterationEvent

GIB = 2**30
ALGORITHM_DEADLINE_SECONDS = 1200
CLEANUP_DEADLINE_SECONDS = 30
Algorithm = Literal["wcc-randomized", "wcc-min-label", "bfs"]
Outcome = Literal["running", "passed", "error", "timeout", "interrupted", "nonconverged", "cleanup_error"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EngineConfig(Record):
    model_config = ConfigDict(frozen=True, strict=True)
    repo: Path
    harness_repo: Path
    output: Path
    vertices: Path
    edges: Path
    binary: Path
    mode: Literal["local", "process-cluster"]
    algorithm: Algorithm
    source: int = Field(strict=True, ge=-(2**63), le=2**63 - 1)
    partitions: Literal[16]
    pool_bytes: int = Field(strict=True)
    native_quota: Literal[268435456]

    @model_validator(mode="after")
    def envelope(self) -> EngineConfig:
        expected = (30 if self.mode == "local" else 10) * GIB
        if self.pool_bytes != expected:
            raise ValueError("requires 30 GiB local or 10 GiB per cluster process")
        if any(not p.is_absolute() for p in (self.repo, self.harness_repo, self.output,
                                              self.vertices, self.edges, self.binary)):
            raise ValueError("all configured paths must be absolute")
        return self


class CleanupError(Record):
    operation: str
    error: str


@dataclass(slots=True)
class CleanupSink:
    """Typed adapter for the frozen runtime's append-only cleanup interface."""

    records: list[CleanupError] = field(default_factory=list)

    def append(self, value: Mapping[str, str]) -> None:
        self.records.append(CleanupError(operation=value["operation"], error=value["error"]))


class PhaseRecord(Record):
    name: str
    status: Literal["start", "end", "error"]
    recorded_utc: str
    elapsed_seconds: float
    duration_seconds: float | None = None
    error: str | None = None


class ObservedEvent(Record):
    elapsed_seconds: float
    event: IterationEvent


class RoundRecord(Record):
    iteration: int
    duration_seconds: float


class OutputField(Record):
    name: str
    type: str
    nullable: bool


class ResultMetadata(Record):
    algorithm: str
    method: str | None
    seed: int | None
    iterations: int
    converged: bool | None


class CgroupSnapshot(Record):
    model_config = ConfigDict(extra="ignore")
    memory_current: str | None = Field(alias="memory.current")
    memory_peak: str | None = Field(alias="memory.peak")
    memory_max: str | None = Field(alias="memory.max")
    memory_swap_max: str | None = Field(alias="memory.swap.max")
    memory_events: str | None = Field(alias="memory.events")
    memory_stat: str | None = Field(alias="memory.stat")
    cpu_max: str | None = Field(alias="cpu.max")
    cpu_stat: str | None = Field(alias="cpu.stat")
    cpuset_cpus_effective: str | None = Field(alias="cpuset.cpus.effective")


class ModuleOrigins(Record):
    algorithms: str
    runtime: str
    measurement: str
    python_executable: str
    python_version: str


class ErrorRecord(Record):
    type: str
    message: str
    traceback: str


class EngineReceipt(Record):
    schema_version: Literal[1] = 1
    verdict_scope: Literal["engine execution and cleanup only; oracle outside child"] = (
        "engine execution and cleanup only; oracle outside child")
    config: EngineConfig
    started_utc: str
    finished_utc: str | None = None
    outcome: Outcome = "running"
    declared_controller_pin: str = "f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a"
    declared_runtime_pin: str = "56194b170155301ba91077f0ba3df31fe2c78b6b"
    declared_native_pin: str = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
    identity_guard_scope: str = "supervisor verifies hashes/pins; child records and checks import locations"
    origins: ModuleOrigins | None = None
    driver_pid: int | None = None
    phases: list[PhaseRecord] = Field(default_factory=list)
    events: list[ObservedEvent] = Field(default_factory=list)
    rounds: list[RoundRecord] = Field(default_factory=list)
    incomplete_rounds: list[int] = Field(default_factory=list)
    result: ResultMetadata | None = None
    output_schema: list[OutputField] = Field(default_factory=list)
    output_projection: list[str] = Field(default_factory=list)
    timing_scope: str = "phase offsets begin after config parsing; supervisor times complete process launch through exit"
    snapshots_in_engine_boundary: bool = True
    snapshot_timing_hook: str = "delegates the original _snapshot once, without extra actions"
    wcc_canonical_labels: Literal[True] = True
    bfs_directed: Literal[True] = True
    bfs_public_method: Literal["frontier"] = "frontier"
    bfs_internal_columns: list[str] = Field(default_factory=lambda: ["distance", "hops", "parent"])
    bfs_unreachable: str = "native NULL distance; external oracle adapts to graphframes Int32 maximum"
    seed: Literal[42] = 42
    max_iterations: int
    threads_per_process: Literal[16] = 16
    worker_count: int
    worker_task_slots: Literal[64] = 64
    potential_pool_total_bytes: int = 30 * GIB
    pool_type: Literal["greedy"] = "greedy"
    logging: Literal["warn"] = "warn"
    plan_capture: Literal[False] = False
    repartition_checkpoints: Literal[True] = True
    rpc_max_retries: Literal[1] = 1
    algorithm_deadline_seconds: int = ALGORITHM_DEADLINE_SECONDS
    cleanup_deadline_seconds: int = CLEANUP_DEADLINE_SECONDS
    before: CgroupSnapshot | None = None
    after: CgroupSnapshot | None = None
    guest_steal_fraction: float | None = None
    cleanup_errors: list[CleanupError] = Field(default_factory=list)
    staging_payload_after_shutdown: list[str] = Field(default_factory=list)
    error: ErrorRecord | None = None


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_receipt(path: Path, receipt: EngineReceipt) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2, by_alias=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append_record(path: Path, record: Record) -> None:
    with path.open("a") as stream:
        stream.write(record.model_dump_json(exclude_none=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(slots=True)
class Journal:
    receipt: EngineReceipt
    start: float

    def persist(self) -> None:
        atomic_receipt(self.receipt.config.output / "engine-receipt.json", self.receipt)

    @contextlib.contextmanager
    def phase(self, name: str) -> Iterator[None]:
        began = time.perf_counter()
        self.mark(PhaseRecord(name=name, status="start", recorded_utc=utc(), elapsed_seconds=began - self.start))
        try:
            yield
        except BaseException as error:
            self.mark(PhaseRecord(name=name, status="error", recorded_utc=utc(),
                                 elapsed_seconds=time.perf_counter() - self.start,
                                 duration_seconds=time.perf_counter() - began, error=repr(error)))
            raise
        else:
            self.mark(PhaseRecord(name=name, status="end", recorded_utc=utc(),
                                 elapsed_seconds=time.perf_counter() - self.start,
                                 duration_seconds=time.perf_counter() - began))

    def mark(self, event: PhaseRecord) -> None:
        self.receipt.phases.append(event)
        append_record(self.receipt.config.output / "phases.jsonl", event)
        self.persist()

    def observe(self, event: IterationEvent) -> None:
        row = ObservedEvent(elapsed_seconds=time.perf_counter() - self.start, event=event)
        self.receipt.events.append(row)
        append_record(self.receipt.config.output / "events.jsonl", row)


@contextlib.contextmanager
def snapshot_phase(journal: Journal) -> Iterator[None]:
    original = algorithms._snapshot

    def measured(run: StagingRun, vertices: DataFrame, edges: DataFrame,
                 edge_columns: tuple[str, ...] = ("src", "dst"), *,
                 count_vertices: bool = True) -> tuple[DataFrame, DataFrame, int | None]:
        with journal.phase("input_snapshot"):
            return cast(tuple[DataFrame, DataFrame, int | None],
                        original(run, vertices, edges, edge_columns, count_vertices=count_vertices))

    algorithms._snapshot = measured
    try:
        yield
    finally:
        algorithms._snapshot = original


def interrupted(signum: int, _frame: FrameType | None) -> None:
    if signum == signal.SIGALRM:
        raise TimeoutError("engine or cleanup phase deadline")
    raise InterruptedError(f"engine interrupted by signal {signum}")


def cleanup(journal: Journal, sink: CleanupSink, name: str, action: Callable[[], Any]) -> None:
    attempted = False
    try:
        signal.alarm(CLEANUP_DEADLINE_SECONDS)
        with journal.phase(name):
            attempted = True
            action()
    except BaseException as error:  # noqa: BLE001 — interruption must not skip owned cleanup.
        sink.records.append(CleanupError(operation=name, error=repr(error)))
        if not attempted:
            # A failed diagnostic write must not prevent owned-resource cleanup.
            try:
                signal.alarm(CLEANUP_DEADLINE_SECONDS)
                action()
            except BaseException as fallback_error:  # noqa: BLE001 — retain fallback cleanup failures.
                sink.records.append(CleanupError(operation=name + "_after_journal_error", error=repr(fallback_error)))
    finally:
        signal.alarm(0)


def execute(config: EngineConfig, journal: Journal, sink: CleanupSink) -> None:
    receipt = journal.receipt
    receipt.before = CgroupSnapshot.model_validate(measurement.cgroup_snapshot())
    ticks = measurement.cpu_ticks()
    server = runtime.server(config.binary, config.output, config.mode, config.partitions, 16,
                            config.native_quota, sink, worker_task_slots=64,
                            sail_pool_bytes=config.pool_bytes, http2_keepalive_timeout=120)
    spark: SparkSession | None = None
    handle: GraphResult | None = None
    entered = False
    try:
        with journal.phase("server_startup"):
            endpoint_and_pid = server.__enter__()
            entered = True
            endpoint, receipt.driver_pid = endpoint_and_pid
        with journal.phase("session_startup"):
            spark = SparkSession.builder.remote(endpoint).create()
            spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100,
                                                          max_backoff=100, jitter=0)])
            if spark.sql("SELECT 1 AS ready").first().ready != 1:
                raise RuntimeError("server readiness failed")
        with journal.phase("input_handles"):
            vertices = spark.read.parquet(config.vertices.as_uri())
            edges = spark.read.parquet(config.edges.as_uri()).selectExpr("source AS src", "target AS dst")
        graph = algorithms.GraphAlgorithms(spark, observer=journal.observe, record_plans=False,
                                           repartition_checkpoints=True)
        with journal.phase("public_algorithm"), snapshot_phase(journal):
            if config.algorithm == "bfs":
                handle = graph.bfs(vertices, edges, source=config.source, directed=True, method="frontier",
                                   max_iterations=1000, partitions=config.partitions)
            else:
                method: Literal["randomized", "min_label"] = (
                    "randomized" if config.algorithm == "wcc-randomized" else "min_label")
                handle = graph.wcc(vertices, edges, method=method, seed=42, canonical_labels=True,
                                   max_iterations=100, partitions=config.partitions)
        receipt.result = ResultMetadata(algorithm=handle.algorithm, method=handle.method, seed=handle.seed,
                                        iterations=handle.iterations, converged=handle.converged)
        if handle.converged is not True:
            raise algorithms.ConvergenceError("public algorithm did not converge")
        with journal.phase("result_export"):
            receipt.output_projection = ["id", "distance"] if config.algorithm == "bfs" else ["id", "component"]
            frame = handle.frame.select(*receipt.output_projection)
            receipt.output_schema = [OutputField(name=f.name, type=f.dataType.simpleString(), nullable=f.nullable)
                                     for f in frame.schema.fields]
            frame.write.mode("error").parquet((config.output / "result").as_uri())
    finally:
        active_error = sys.exc_info()
        if handle is not None:
            cleanup(journal, sink, "result_close", handle.close)
        if spark is not None:
            cleanup(journal, sink, "session_stop", spark.stop)
        if entered:
            cleanup(journal, sink, "server_shutdown", lambda: server.__exit__(*active_error))
        try:
            receipt.after = CgroupSnapshot.model_validate(measurement.cgroup_snapshot())
            receipt.guest_steal_fraction = measurement.steal_fraction(ticks, measurement.cpu_ticks())
        except BaseException as observation_error:  # noqa: BLE001 — preserve the active algorithm failure.
            sink.records.append(CleanupError(operation="shutdown_observation", error=repr(observation_error)))


def summarize_rounds(receipt: EngineReceipt) -> None:
    starts: dict[int, float] = {}
    for row in receipt.events:
        event = row.event
        if event.kind == "iteration_start":
            if event.iteration in starts:
                raise RuntimeError("duplicate iteration start")
            starts[event.iteration] = row.elapsed_seconds
        elif event.kind == "iteration_end":
            if event.iteration not in starts:
                raise RuntimeError("iteration end without start")
            receipt.rounds.append(RoundRecord(iteration=event.iteration,
                                              duration_seconds=row.elapsed_seconds - starts.pop(event.iteration)))
    receipt.incomplete_rounds = sorted(starts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    config = EngineConfig.model_validate_json(parser.parse_args().config.read_text())
    config.output.mkdir(parents=True, exist_ok=True)
    for name in ("engine-receipt.json", "engine-receipt.json.tmp", "phases.jsonl", "events.jsonl", "result", "staging"):
        if (config.output / name).exists() or (config.output / name).is_symlink():
            raise FileExistsError(f"refusing existing engine evidence: {name}")
    for name in ("phases.jsonl", "events.jsonl"):
        (config.output / name).touch(exist_ok=False)
    receipt = EngineReceipt(config=config, started_utc=utc(), max_iterations=1000 if config.algorithm == "bfs" else 100,
                            worker_count=0 if config.mode == "local" else 2)
    journal, sink = Journal(receipt, time.perf_counter()), CleanupSink()
    journal.persist()
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(signum, interrupted)
    os.environ.update(SAIL_BENCHMARK_RUST_LOG="warn", SPARK_CONNECT_MODE_ENABLED="1",
                      PYTHONDONTWRITEBYTECODE="1", SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS="900",
                      SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS="86400")
    try:
        receipt.origins = ModuleOrigins(algorithms=str(Path(algorithms.__file__).resolve()),
                                       runtime=str(Path(runtime.__file__).resolve()),
                                       measurement=str(Path(measurement.__file__).resolve()),
                                       python_executable=sys.executable, python_version=sys.version)
        expected_algorithms = config.repo / "examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py"
        if Path(receipt.origins.algorithms) != expected_algorithms.resolve():
            raise RuntimeError("Pecan import does not come from configured source")
        expected_benchmarks = config.harness_repo / "examples/extensions/benchmarks"
        if (Path(receipt.origins.runtime) != (expected_benchmarks / "runtime.py").resolve()
                or Path(receipt.origins.measurement) != (expected_benchmarks / "measurement.py").resolve()):
            raise RuntimeError("benchmark helper import does not come from configured frozen harness")
        signal.alarm(ALGORITHM_DEADLINE_SECONDS)
        execute(config, journal, sink)
        if receipt.result is None:
            raise RuntimeError("missing exported algorithm metadata")
    except BaseException as error:  # noqa: BLE001 — cancellation and timeout are recorded outcomes.
        receipt.outcome = ("nonconverged" if isinstance(error, algorithms.ConvergenceError)
                           else "timeout" if isinstance(error, TimeoutError)
                           else "interrupted" if isinstance(error, (InterruptedError, KeyboardInterrupt)) else "error")
        receipt.error = ErrorRecord(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
        try:
            summarize_rounds(receipt)
            staging = config.output / "staging"
            receipt.staging_payload_after_shutdown = [str(p.relative_to(staging)) for p in staging.rglob("*")
                                                      if p.is_symlink() or not p.is_dir()]
            if receipt.after is None:
                receipt.after = CgroupSnapshot.model_validate(measurement.cgroup_snapshot())
            if receipt.outcome == "running":
                receipt.outcome = ("cleanup_error" if sink.records or receipt.staging_payload_after_shutdown
                                   or receipt.incomplete_rounds else "passed")
        except BaseException as error:  # noqa: BLE001 — final observation cannot mask owned cleanup.
            sink.records.append(CleanupError(operation="final_observation", error=repr(error)))
            if receipt.outcome == "running":
                receipt.outcome = "cleanup_error"
        receipt.cleanup_errors = sink.records
        receipt.finished_utc = utc()
        journal.persist()
    print(json.dumps({"outcome": receipt.outcome, "receipt": str(config.output / "engine-receipt.json")}), flush=True)
    return 0 if receipt.outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
