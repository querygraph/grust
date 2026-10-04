"""B8 isolated query shapes, with engine startup/export/cleanup inside the child.

This is not complete WCC: representatives exports the first contraction round's
active endpoint map; min-label exports its initial propagation update. The
array form of min-label is a named whole-update rewrite, not a direct replacement
of heterogeneous V+E union. Input snapshots, identical preparation, and explain
planning are included in launch through exit; no counts or data oracle run here.
Lifecycle/journal adaptation: A2 engine_pecan.py a036971bd6cbb1911a800618485977ecc219b2a155f61d31265d74bed1a5435e.
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
from typing import Any, Literal

import measurement
import runtime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyspark.sql import DataFrame
from pyspark.sql.connect import functions as F
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import algorithms, wcc_randomized
from pyspark_pecan.lifecycle import GraphResult
from pyspark_pecan.staging import StagingRun

Shape = Literal['adjacency', 'representatives', 'min-label-initial-round']
Variant = Literal['union', 'array-explode']
Outcome = Literal['running', 'passed', 'error', 'timeout', 'interrupted', 'cleanup_error']
DEADLINE_SECONDS = 1200
CLEANUP_SECONDS = 30


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ShapeConfig(Record):
    model_config = ConfigDict(frozen=True, strict=True)
    repo: Path
    harness_repo: Path
    output: Path
    vertices: Path
    edges: Path
    binary: Path
    mode: Literal['local'] = 'local'
    partitions: Literal[16] = 16
    pool_bytes: Literal[32212254720] = 32212254720
    native_quota: Literal[268435456] = 268435456
    shape: Shape
    variant: Variant

    @model_validator(mode='after')
    def paths(self) -> ShapeConfig:
        if any(not p.is_absolute() for p in (self.repo, self.harness_repo, self.output,
                                             self.vertices, self.edges, self.binary)):
            raise ValueError('all configured paths must be absolute')
        return self


class CleanupError(Record):
    operation: str
    error: str


@dataclass(slots=True)
class CleanupSink:
    records: list[CleanupError] = field(default_factory=list)

    def append(self, value: Mapping[str, str]) -> None:
        self.records.append(CleanupError(operation=value['operation'], error=value['error']))


class Phase(Record):
    name: str
    status: Literal['start', 'end', 'error']
    recorded_utc: str
    elapsed_seconds: float
    duration_seconds: float | None = None
    error: str | None = None


class CapturedPlan(Record):
    relation: str
    file: str
    scope: str = 'explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper'


class OutputField(Record):
    name: str
    type: str
    nullable: bool


class Origins(Record):
    algorithms: str
    wcc_randomized: str
    runtime: str
    measurement: str
    python_executable: str
    python_version: str


class Coefficients(Record):
    seed: Literal[42] = 42
    contraction_round: Literal[1] = 1
    a_signed_bigint: int
    b_signed_bigint: int
    mapping: str = 'actual f3b SplitMix64 coefficients and gf_axpb GF(2^64); grouped MIN/least uses signed BIGINT order'


class Cgroups(Record):
    model_config = ConfigDict(extra='ignore')
    memory_current: str | None = Field(alias='memory.current')
    memory_peak: str | None = Field(alias='memory.peak')
    memory_max: str | None = Field(alias='memory.max')
    memory_swap_max: str | None = Field(alias='memory.swap.max')
    memory_events: str | None = Field(alias='memory.events')
    cpu_max: str | None = Field(alias='cpu.max')
    cpu_stat: str | None = Field(alias='cpu.stat')


class Failure(Record):
    type: str
    message: str
    traceback: str


class Receipt(Record):
    schema_version: Literal[1] = 1
    config: ShapeConfig
    started_utc: str
    finished_utc: str | None = None
    outcome: Outcome = 'running'
    verdict_scope: str = 'engine execution/export/cleanup only; full physical oracle outside child'
    controller_pin: str = 'f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'
    runtime_pin: str = '56194b170155301ba91077f0ba3df31fe2c78b6b'
    native_pin: str = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
    identity_guard_scope: str = 'parent verifies hashes/pins; child checks exact module locations'
    timing_scope: str = 'parent launch through exit includes startup, reads, snapshots, preparation, explain, writes, and cleanup'
    actual_method: str
    shape_scope: str
    coefficients: Coefficients | None = None
    origins: Origins | None = None
    driver_pid: int | None = None
    phases: list[Phase] = Field(default_factory=list)
    plans: list[CapturedPlan] = Field(default_factory=list)
    output_schema: list[OutputField] = Field(default_factory=list)
    output_projection: list[str] = Field(default_factory=list)
    snapshots_in_engine_boundary: Literal[True] = True
    preparation_in_engine_boundary: Literal[True] = True
    planning_in_engine_boundary: Literal[True] = True
    threads_per_process: Literal[16] = 16
    worker_task_slots: Literal[64] = 64
    pool_type: Literal['greedy'] = 'greedy'
    logging: Literal['warn'] = 'warn'
    repartition_checkpoints: Literal[True] = True
    rpc_max_retries: Literal[1] = 1
    result_exported: bool = False
    before: Cgroups | None = None
    after: Cgroups | None = None
    guest_steal_fraction: float | None = None
    cleanup_errors: list[CleanupError] = Field(default_factory=list)
    staging_payload_after_shutdown: list[str] = Field(default_factory=list)
    error: Failure | None = None


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_receipt(path: Path, receipt: Receipt) -> None:
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w') as stream:
        stream.write(receipt.model_dump_json(indent=2, by_alias=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@dataclass(slots=True)
class Journal:
    receipt: Receipt
    start: float

    def persist(self) -> None:
        atomic_receipt(self.receipt.config.output / 'engine-receipt.json', self.receipt)

    def mark(self, phase: Phase) -> None:
        self.receipt.phases.append(phase)
        with (self.receipt.config.output / 'phases.jsonl').open('a') as stream:
            stream.write(phase.model_dump_json(exclude_none=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self.persist()

    @contextlib.contextmanager
    def phase(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        self.mark(Phase(name=name, status='start', recorded_utc=utc(), elapsed_seconds=start - self.start))
        try:
            yield
        except BaseException as error:
            self.mark(Phase(name=name, status='error', recorded_utc=utc(), elapsed_seconds=time.perf_counter() - self.start,
                            duration_seconds=time.perf_counter() - start, error=repr(error)))
            raise
        else:
            self.mark(Phase(name=name, status='end', recorded_utc=utc(), elapsed_seconds=time.perf_counter() - self.start,
                            duration_seconds=time.perf_counter() - start))


@contextlib.contextmanager
def snapshot_phase(journal: Journal) -> Iterator[None]:
    original = algorithms._snapshot

    def measured(run: StagingRun, vertices: DataFrame, edges: DataFrame,
                 edge_columns: tuple[str, ...] = ('src', 'dst'), *,
                 count_vertices: bool = True) -> tuple[DataFrame, DataFrame, int | None]:
        with journal.phase('input_snapshot'):
            return original(run, vertices, edges, edge_columns, count_vertices=count_vertices)

    algorithms._snapshot = measured
    try:
        yield
    finally:
        algorithms._snapshot = original


def adjacency(edges: DataFrame, variant: Variant) -> DataFrame:
    if variant == 'union':
        return edges.unionByName(edges.select(F.col('dst').alias('src'), F.col('src').alias('dst'))).distinct()
    pairs = F.array(F.struct(F.col('src').alias('src'), F.col('dst').alias('dst')),
                    F.struct(F.col('dst').alias('src'), F.col('src').alias('dst')))
    return edges.select(F.explode(pairs).alias('pair')).select('pair.src', 'pair.dst').distinct()


def representatives(edges: DataFrame, a: int, b: int, variant: Variant) -> DataFrame:
    if variant == 'union':
        return wcc_randomized.representatives(edges, a, b)
    pairs = F.array(F.struct(F.col('src').alias('id'), wcc_randomized._axpb(a, 'dst', b).alias('neighbour')),
                    F.struct(F.col('dst').alias('id'), wcc_randomized._axpb(a, 'src', b).alias('neighbour')))
    messages = edges.select(F.explode(pairs).alias('pair')).select('pair.id', 'pair.neighbour')
    minima = messages.groupBy('id').agg(F.min('neighbour').alias('neighbour'))
    return minima.select('id', F.least(wcc_randomized._axpb(a, 'id', b), F.col('neighbour')).alias('representative'))


def min_label_initial_round(labels: DataFrame, neighbors: DataFrame, variant: Variant) -> DataFrame:
    if variant == 'union':
        messages = neighbors.join(labels, neighbors.src == labels.id).select(neighbors.dst.alias('id'), labels.component)
        return labels.unionByName(messages).groupBy('id').agg(F.min('component').alias('component'))
    # Whole-update rewrite: old labels repeat for every outgoing adjacency row.
    # MIN is insensitive to these duplicates. The left join keeps isolates.
    owners = labels.select(F.col('id').alias('owner'), F.col('component').alias('old_component'))
    joined = owners.join(neighbors, owners.owner == neighbors.src, 'left')
    pairs = F.array(F.struct(F.col('owner').alias('id'), F.col('old_component').alias('component')),
                    F.struct(F.col('dst').alias('id'), F.col('old_component').alias('component')))
    messages = joined.select(F.explode(pairs).alias('pair')).select('pair.id', 'pair.component').where(F.col('id').isNotNull())
    return messages.groupBy('id').agg(F.min('component').alias('component'))


def planned_materialization(run: StagingRun, frame: DataFrame, journal: Journal, name: str) -> tuple[str, DataFrame]:
    with journal.phase('plan_' + name):
        text = algorithms.physical_plan(frame.repartition(run.partitions))
        file = journal.receipt.config.output / ('plan-' + name + '.txt')
        with file.open('x') as stream:
            stream.write(text + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        journal.receipt.plans.append(CapturedPlan(relation=name, file=file.name))
    with journal.phase('write_' + name):
        return run.materialize(frame)


def build_shape(graph: algorithms.GraphAlgorithms, vertices: DataFrame, edges: DataFrame,
                config: ShapeConfig, journal: Journal) -> GraphResult:
    if config.shape == 'representatives' and 'axpb' not in graph.utils.capabilities:
        raise ValueError('representatives requires actual axpb capability')

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        if config.shape == 'adjacency':
            with journal.phase('build_adjacency'):
                result = adjacency(edges, config.variant)
        elif config.shape == 'representatives':
            with journal.phase('build_representatives'):
                a, b = wcc_randomized.SplitMix64(42).coefficients()
                journal.receipt.coefficients = Coefficients(a_signed_bigint=a, b_signed_bigint=b)
                current = edges.where(F.col('src') != F.col('dst'))
                result = representatives(current, a, b, config.variant)
        else:
            # Both updates use the same source-faithful union/distinct adjacency
            # and initial label checkpoint. Only the whole update differs.
            _, neighbors = planned_materialization(run, adjacency(edges, 'union'), journal, 'initial-adjacency')
            _, labels = planned_materialization(run, vertices.withColumn('component', F.col('id')), journal, 'initial-labels')
            with journal.phase('build_initial_min_label_update'):
                result = min_label_initial_round(labels, neighbors, config.variant)
        path, stored = planned_materialization(run, result, journal, 'shape-result')
        handle = run.finish(path, stored, algorithm='b8-' + config.shape, iterations=1, converged=None)
        handle.method = journal.receipt.actual_method
        return handle

    return graph._run(vertices, edges, config.partitions, None, body, count_vertices=False)


def interrupted(signum: int, _frame: FrameType | None) -> None:
    if signum == signal.SIGALRM:
        raise TimeoutError('engine or cleanup deadline')
    raise InterruptedError(f'engine interrupted by signal {signum}')


def cleanup(journal: Journal, sink: CleanupSink, name: str, action: Callable[[], Any]) -> None:
    attempted = False
    try:
        signal.alarm(CLEANUP_SECONDS)
        with journal.phase(name):
            attempted = True
            action()
    except BaseException as error:  # noqa: BLE001 - interruption must not skip owned cleanup
        sink.records.append(CleanupError(operation=name, error=repr(error)))
        if not attempted:
            try:
                signal.alarm(CLEANUP_SECONDS)
                action()
            except BaseException as fallback:  # noqa: BLE001 - retain fallback cleanup failure
                sink.records.append(CleanupError(operation=name + '_after_journal_error', error=repr(fallback)))
    finally:
        signal.alarm(0)


def execute(config: ShapeConfig, journal: Journal, sink: CleanupSink) -> None:
    receipt = journal.receipt
    receipt.before = Cgroups.model_validate(measurement.cgroup_snapshot())
    ticks = measurement.cpu_ticks()
    server = runtime.server(config.binary, config.output, 'local', 16, 16, config.native_quota,
                            sink, worker_task_slots=64, sail_pool_bytes=config.pool_bytes, http2_keepalive_timeout=120)
    spark: SparkSession | None = None
    handle: GraphResult | None = None
    entered = False
    try:
        with journal.phase('server_startup'):
            endpoint_and_pid = server.__enter__()
            entered = True
            endpoint, receipt.driver_pid = endpoint_and_pid
        with journal.phase('session_startup'):
            spark = SparkSession.builder.remote(endpoint).create()
            spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
            if spark.sql('SELECT 1 AS ready').first().ready != 1:
                raise RuntimeError('server readiness failed')
        with journal.phase('input_handles'):
            vertices = spark.read.parquet(config.vertices.as_uri())
            edges = spark.read.parquet(config.edges.as_uri()).selectExpr('source AS src', 'target AS dst')
        graph = algorithms.GraphAlgorithms(spark, record_plans=False, repartition_checkpoints=True)
        with journal.phase('isolated_shape'), snapshot_phase(journal):
            handle = build_shape(graph, vertices, edges, config, journal)
        with journal.phase('result_export'):
            columns = {'adjacency': ['src', 'dst'], 'representatives': ['id', 'representative'],
                       'min-label-initial-round': ['id', 'component']}[config.shape]
            frame = handle.frame.select(*columns)
            receipt.output_projection = columns
            receipt.output_schema = [OutputField(name=f.name, type=f.dataType.simpleString(), nullable=f.nullable)
                                     for f in frame.schema.fields]
            if any(f.type != 'bigint' for f in receipt.output_schema):
                raise TypeError('shape output must retain raw BIGINT fields')
            frame.write.mode('error').parquet((config.output / 'result').as_uri())
            receipt.result_exported = True
    finally:
        active_error = sys.exc_info()
        if handle is not None:
            cleanup(journal, sink, 'result_close', handle.close)
        if spark is not None:
            cleanup(journal, sink, 'session_stop', spark.stop)
        if entered:
            cleanup(journal, sink, 'server_shutdown', lambda: server.__exit__(*active_error))
        try:
            receipt.after = Cgroups.model_validate(measurement.cgroup_snapshot())
            receipt.guest_steal_fraction = measurement.steal_fraction(ticks, measurement.cpu_ticks())
        except BaseException as error:  # noqa: BLE001 - preserve active failure after owned cleanup
            sink.records.append(CleanupError(operation='shutdown_observation', error=repr(error)))


def check_origins(config: ShapeConfig) -> Origins:
    origins = Origins(algorithms=str(Path(algorithms.__file__).resolve()), wcc_randomized=str(Path(wcc_randomized.__file__).resolve()),
                      runtime=str(Path(runtime.__file__).resolve()), measurement=str(Path(measurement.__file__).resolve()),
                      python_executable=sys.executable, python_version=sys.version)
    package = config.repo / 'examples/extensions/graph-algorithms/src/pyspark_pecan'
    benchmark = config.harness_repo / 'examples/extensions/benchmarks'
    if (Path(origins.algorithms) != (package / 'algorithms.py').resolve()
            or Path(origins.wcc_randomized) != (package / 'wcc_randomized.py').resolve()
            or Path(origins.runtime) != (benchmark / 'runtime.py').resolve()
            or Path(origins.measurement) != (benchmark / 'measurement.py').resolve()):
        raise RuntimeError('shape/module imports do not come from configured exact sources')
    return origins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    config = ShapeConfig.model_validate_json(parser.parse_args().config.read_text())
    config.output.mkdir(parents=True, exist_ok=True)
    if any(config.output.iterdir()):
        raise FileExistsError('refusing existing shape engine evidence')
    (config.output / 'phases.jsonl').touch(exist_ok=False)
    method = (('min-label-whole-update-left-join-array-explode' if config.variant == 'array-explode'
               else 'min-label-labels-union-messages') if config.shape == 'min-label-initial-round'
              else config.shape + '-' + config.variant)
    scope = {'adjacency': 'distinct original and reverse edge pairs',
             'representatives': 'first contraction-round active endpoints only; actual self-loop exclusion; no full WCC partition',
             'min-label-initial-round': 'initial component=id propagation update including isolates; no complete WCC loop'}[config.shape]
    receipt = Receipt(config=config, started_utc=utc(), actual_method=method, shape_scope=scope)
    journal, sink = Journal(receipt, time.perf_counter()), CleanupSink()
    journal.persist()
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(signum, interrupted)
    os.environ.update(SAIL_BENCHMARK_RUST_LOG='warn', SPARK_CONNECT_MODE_ENABLED='1', PYTHONDONTWRITEBYTECODE='1',
                      SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS='900', SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS='86400')
    try:
        receipt.origins = check_origins(config)
        signal.alarm(DEADLINE_SECONDS)
        execute(config, journal, sink)
        if not receipt.result_exported:
            raise RuntimeError('missing complete shape export')
    except BaseException as error:  # noqa: BLE001 - record cancellation/timeout without skipping cleanup
        receipt.outcome = ('timeout' if isinstance(error, TimeoutError) else 'interrupted'
                           if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'error')
        receipt.error = Failure(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
        try:
            staging = config.output / 'staging'
            receipt.staging_payload_after_shutdown = [str(p.relative_to(staging)) for p in staging.rglob('*')
                                                      if p.is_symlink() or not p.is_dir()]
            if receipt.after is None:
                receipt.after = Cgroups.model_validate(measurement.cgroup_snapshot())
            if receipt.outcome == 'running':
                receipt.outcome = 'cleanup_error' if sink.records or receipt.staging_payload_after_shutdown else 'passed'
        except BaseException as error:  # noqa: BLE001 - final observation must remain a failed outcome
            sink.records.append(CleanupError(operation='final_observation', error=repr(error)))
            if receipt.outcome == 'running':
                receipt.outcome = 'cleanup_error'
        receipt.cleanup_errors = sink.records
        receipt.finished_utc = utc()
        journal.persist()
    print(json.dumps({'outcome': receipt.outcome, 'receipt': str(config.output / 'engine-receipt.json')}), flush=True)
    return 0 if receipt.outcome == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
