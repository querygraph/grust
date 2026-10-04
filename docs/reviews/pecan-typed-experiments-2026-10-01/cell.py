"""One fresh-container matched Pecan WCC cell; source imports come from PYTHONPATH.

No server plan capture or extra Explain calls. This runner does not implement a
trusted-input API: it measures the public API of each exact selected revision.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import measurement
import oracle as oracle_module
import pyarrow as pa
import pyarrow.parquet as pq
import runtime
from oracle import Correctness, Mismatch, load_oracle, require, sha, verify_output
from pydantic import BaseModel, ConfigDict, Field
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import algorithms

BASELINE = "cab6bacc0ad0d1fc8b3070e9e4267e99751909fe"
CANDIDATE = "6ae2e43a903c2cee02da170465c922c72b76198e"
RUNTIME = "56194b170155301ba91077f0ba3df31fe2c78b6b"
NATIVE = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
BINARY = Path("/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release")
BINARY_SHA = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
NATIVE_SHA = "eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50"
VERTICES_SHA = "0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa"
EDGES_SHA = "70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f"
REFERENCE_SHA = "b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc"
ROWS, EDGE_ROWS, MAX_ID, GIB = 3774768, 16518947, 6009554, 2**30
Outcome = Literal["error", "passed", "mismatch", "nonconverged", "timeout", "interrupted", "oom", "integrity_error"]


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repo: Path
    controller_sha: Literal["cab6bacc0ad0d1fc8b3070e9e4267e99751909fe", "6ae2e43a903c2cee02da170465c922c72b76198e"]
    harness_repo: Path
    vertices: Path
    edges: Path
    reference: Path
    output: Path
    mode: Literal["local", "process-cluster"]
    method: Literal["randomized", "randomized_fused"] = "randomized_fused"
    timeout: int = Field(default=1200, ge=1, le=1200)


class Event(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    kind: Literal["iteration_start", "iteration_end", "certificate"]
    algorithm: str
    iteration: int = Field(ge=0)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    started_utc: str
    finished_utc: str | None = None
    outcome: Outcome = "error"
    arguments: CellConfig
    source_pins: dict[str, str]
    helpers_sha256: dict[str, str]
    resources: dict[str, int | str]
    boundaries: dict[str, str]
    packages: dict[str, str] = Field(default_factory=dict)
    identities: dict[str, Any] = Field(default_factory=dict)
    inputs_before: dict[str, str] = Field(default_factory=dict)
    inputs_after: dict[str, str] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    rounds: dict[str, Any] = Field(default_factory=dict)
    cgroups: dict[str, dict[str, str | None]] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    guest_steal_fraction: float | None = None
    correctness: Correctness | None = None
    cleanup_errors: list[dict[str, str]] = Field(default_factory=list)
    staging_files_after_shutdown: list[str] = Field(default_factory=list)
    error: str | None = None
    integrity_error: str | None = None


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event(event: object) -> dict[str, Any]:
    """Preserve both revisions' metrics; remove only run path and unset fields."""
    if isinstance(event, Mapping):
        values = dict(event)
    elif isinstance(event, BaseModel) and callable(getattr(event, "as_dict", None)):
        values = event.as_dict()
    else:
        raise ValueError("unexpected observer event type")
    values = {key: value for key, value in values.items() if key != "run_path" and value is not None}
    normalized = Event.model_validate(values).model_dump()
    json.dumps(normalized, allow_nan=False)
    return normalized


def append(path: Path, value: dict[str, Any]) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps({"recorded_utc": utc(), **value}, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def source_guard(repo: Path, commit: str) -> None:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], env=env, text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], env=env, text=True).strip()
    require(head == commit and not dirty, f"source must be clean at {commit}")


def identity(config: CellConfig) -> dict[str, Any]:
    source_guard(config.repo, config.controller_sha)
    source_guard(config.harness_repo, CANDIDATE)
    package = config.repo / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    harness = config.harness_repo / "examples/extensions/benchmarks"
    require(Path(algorithms.__file__).resolve() == package / "algorithms.py", "wrong Pecan import")
    require(Path(runtime.__file__).resolve() == harness / "runtime.py"
            and Path(measurement.__file__).resolve() == harness / "measurement.py", "wrong fixed harness imports")
    require(sha(BINARY) == BINARY_SHA, "runtime binary identity mismatch")
    native = runtime.native_package_identity()
    require(NATIVE_SHA in [value for key, value in native["files_sha256"].items() if key.endswith(".so")],
            "native binary identity mismatch")
    return {"native": native, "binary_sha256": sha(BINARY),
            "harness_files": {name: sha(harness / name) for name in ("runtime.py", "measurement.py")},
            "package_files": {str(path.relative_to(package)): sha(path) for path in sorted(package.rglob("*.py"))}}


def deadline(signum: int, frame: Any) -> None:
    raise TimeoutError("cell phase timeout")


def interrupted(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt(f"operator signal {signum}")


@contextlib.contextmanager
def input_timers(receipt: Receipt) -> Iterator[None]:
    """Delegate original calls once; residual includes control overhead, not just audits."""
    schema, snapshot, materialize = algorithms._check_input_schema, algorithms._snapshot, algorithms.StagingRun.materialize

    def timed_schema(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return schema(*args, **kwargs)
        finally:
            receipt.timings["input_schema_seconds"] = time.perf_counter() - start

    def timed_snapshot(*args: Any, **kwargs: Any) -> Any:
        parsed = urlparse(args[0].path)
        require(parsed.scheme == "file" and Path(unquote(parsed.path)).resolve().is_relative_to(
            (receipt.arguments.output / "staging").resolve()), "unexpected GraphUtils staging root")
        durations: list[float] = []
        start = time.perf_counter()

        def timed_materialize(*args: Any, **kwargs: Any) -> Any:
            began = time.perf_counter()
            try:
                return materialize(*args, **kwargs)
            finally:
                durations.append(time.perf_counter() - began)

        algorithms.StagingRun.materialize = timed_materialize
        try:
            return snapshot(*args, **kwargs)
        finally:
            algorithms.StagingRun.materialize = materialize
            total = time.perf_counter() - start
            receipt.timings.update(input_snapshot_seconds=total, input_snapshot_materialize_seconds=durations,
                                   input_snapshot_residual_seconds=total - sum(durations))

    algorithms._check_input_schema, algorithms._snapshot = timed_schema, timed_snapshot
    try:
        yield
    finally:
        algorithms._check_input_schema, algorithms._snapshot = schema, snapshot
        algorithms.StagingRun.materialize = materialize


def round_summary(events: list[dict[str, Any]], ready: float | None) -> dict[str, Any]:
    starts: dict[int, float] = {}
    durations: list[dict[str, int | float]] = []
    for event in events:
        iteration = event["iteration"]
        if event["kind"] == "iteration_start":
            require(iteration not in starts, "duplicate iteration start")
            starts[iteration] = event["elapsed_seconds"]
        elif event["kind"] == "iteration_end":
            require(iteration in starts, "iteration end without start")
            durations.append({"iteration": iteration, "seconds": event["elapsed_seconds"] - starts.pop(iteration)})
    first = next((event["elapsed_seconds"] for event in events if event["kind"] == "iteration_start"), None)
    last = next((event["elapsed_seconds"] for event in reversed(events) if event["kind"] == "iteration_end"), None)
    return {"completed_round_durations": durations, "incomplete_rounds": sorted(starts),
            "pre_first_round_seconds": first, "post_last_round_seconds": ready - last if ready is not None and last is not None else None}


def execute(config: CellConfig, receipt: Receipt) -> None:
    cg = measurement.cgroup_snapshot()
    receipt.cgroups["before"] = cg
    quota, period = map(int, cg["cpu.max"].split())
    require(int(cg["memory.max"]) == 32 * GIB and int(cg["memory.swap.max"]) == 0 and quota == 16 * period,
            "requires 16-CPU/32-GiB/no-extra-swap cgroup")
    ticks = measurement.cpu_ticks()
    sampler = measurement.Sampler(config.output / "memory-samples.jsonl", interval=1.0,
                                  watch={"staging": config.output / "staging"}, directory_every=1)
    handle: Any = None
    spark: Any = None
    start: float | None = None
    try:
        with sampler:
            startup = time.perf_counter()
            with runtime.server(BINARY, config.output, config.mode, 16, 16, 256 * 2**20, receipt.cleanup_errors,
                                worker_task_slots=64, sail_pool_bytes=(24 if config.mode == "local" else 8) * GIB,
                                http2_keepalive_timeout=120) as (endpoint, pid):
                receipt.identities["driver_pid"] = pid
                try:
                    signal.alarm(120)
                    spark = SparkSession.builder.remote(endpoint).create()
                    spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
                    require(spark.sql("SELECT 1 AS ready").first().ready == 1, "server not ready")
                    receipt.timings["startup_seconds"] = time.perf_counter() - startup
                    vertices = spark.read.parquet(config.vertices.as_uri())
                    edges = spark.read.parquet(config.edges.as_uri()).selectExpr("source AS src", "target AS dst")
                    sampler.mark("execute")
                    receipt.cgroups["execution_before"] = measurement.cgroup_snapshot()
                    signal.alarm(config.timeout)
                    start = time.perf_counter()

                    def observe(event: object) -> None:
                        normalized = {**normalize_event(event), "elapsed_seconds": time.perf_counter() - start}
                        receipt.events.append(normalized)
                        append(config.output / "events.jsonl", normalized)

                    graph = algorithms.GraphAlgorithms(spark, observer=observe, record_plans=False,
                                                       repartition_checkpoints=True)
                    with input_timers(receipt):
                        handle = graph.wcc(vertices, edges, method=config.method, seed=42, partitions=16, max_iterations=100)
                    receipt.timings.update(algorithm_ready_seconds=time.perf_counter() - start,
                                           iterations=handle.iterations, converged=handle.converged)
                    if not handle.converged:
                        raise algorithms.ConvergenceError("WCC did not converge")
                    export = time.perf_counter()
                    handle.frame.select("id", "component").write.mode("error").parquet((config.output / "result").as_uri())
                    receipt.timings.update(end_to_end_seconds=time.perf_counter() - start,
                                           export_seconds=time.perf_counter() - export)
                    receipt.cgroups["execution_after"] = measurement.cgroup_snapshot()
                    sampler.mark("verification")
                    signal.alarm(config.timeout)
                    verify = time.perf_counter()
                    expected = load_oracle(config.reference, REFERENCE_SHA, ROWS, MAX_ID)
                    receipt.timings["oracle_load_seconds"] = time.perf_counter() - verify
                    receipt.correctness = verify_output(config.output / "result", expected, ROWS)
                    require(receipt.correctness.components == 3627, "unexpected oracle component count")
                    receipt.timings["verification_seconds"] = time.perf_counter() - verify
                finally:
                    signal.alarm(0)
                    sampler.mark("cleanup")
                    actions: list[tuple[str, Callable[[], Any] | None]] = [
                        ("result", handle.close if handle is not None else None),
                        ("session", spark.stop if spark is not None else None)]
                    for name, action in actions:
                        if action is not None:
                            try:
                                signal.alarm(30)
                                action()
                            except BaseException as error:
                                receipt.cleanup_errors.append({"operation": name, "error": repr(error)})
                            finally:
                                signal.alarm(0)
    finally:
        receipt.memory = sampler.receipt()
        receipt.cgroups["after"] = measurement.cgroup_snapshot()
        receipt.guest_steal_fraction = measurement.steal_fraction(ticks, measurement.cpu_ticks())
        receipt.rounds = round_summary(receipt.events, receipt.timings.get("algorithm_ready_seconds"))
        receipt.staging_files_after_shutdown = [str(path.relative_to(config.output))
                                              for path in (config.output / "staging").rglob("*") if path.is_file()]
        if start is not None and "end_to_end_seconds" not in receipt.timings:
            receipt.timings["elapsed_until_error_seconds"] = time.perf_counter() - start
    require(not receipt.cleanup_errors and sampler.error is None and not receipt.staging_files_after_shutdown,
            "cleanup/sampler error or retained staging")
    require(not receipt.rounds["incomplete_rounds"] and receipt.correctness is not None, "incomplete result")


def input_hashes(config: CellConfig) -> dict[str, str]:
    return {str(path): sha(path) for path in (config.vertices, config.edges, config.reference)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "harness-repo", "vertices", "edges", "reference", "output"):
        parser.add_argument("--" + name, type=lambda text: Path(text).resolve(), required=True)
    parser.add_argument("--controller-sha", choices=[BASELINE, CANDIDATE], required=True)
    parser.add_argument("--mode", choices=["local", "process-cluster"], required=True)
    parser.add_argument("--method", choices=["randomized", "randomized_fused"], default="randomized_fused")
    parser.add_argument("--timeout", type=int, default=1200)
    config = CellConfig.model_validate(vars(parser.parse_args()))
    config.output.mkdir(parents=True, exist_ok=False)
    helpers = {str(Path(__file__).resolve()): sha(Path(__file__)),
               str(Path(oracle_module.__file__).resolve()): sha(Path(oracle_module.__file__))}
    receipt = Receipt(started_utc=utc(), arguments=config, helpers_sha256=helpers,
        source_pins={"controller": config.controller_sha, "harness": CANDIDATE, "runtime": RUNTIME, "native": NATIVE},
        resources={"cpus": 16, "memory_bytes": 32 * GIB, "pool_per_process_bytes": (24 if config.mode == "local" else 8) * GIB,
                   "potential_pool_total_bytes": 24 * GIB, "native_quota_per_process_bytes": 256 * 2**20,
                   "potential_native_total_bytes": (1 if config.mode == "local" else 3) * 256 * 2**20,
                   "partitions": 16, "threads_per_process": 16, "worker_count": 0 if config.mode == "local" else 2,
                   "worker_slots": 64, "log_filter": "warn", "sampler_interval_seconds": 1},
        boundaries={"timer": "lazy input handles through public WCC and result export; excludes startup, input hashes, oracle/physical checks",
                    "snapshot": "original snapshot call; materializations timed inside; residual includes validations/counts where present and control overhead",
                    "diagnostics": "same durable observer logs and warning server filter; no plan capture or Explain RPC; sampler sleeps 1s AFTER each scan",
                    "pool": "sum of nominal per-process pools is not an enforceable shared RSS budget",
                    "steal": "whole Linux VM during server lifecycle; not host quietness proof",
                    "interpretation": "shared-host source comparison; no dedicated speed rating or isolated attribution to individual changes"})
    expected = {str(config.vertices): VERTICES_SHA, str(config.edges): EDGES_SHA, str(config.reference): REFERENCE_SHA}
    initial: dict[str, Any] | None = None
    try:
        require(Path("/.dockerenv").exists() and Path("/proc/stat").exists(), "requires fresh isolated Linux container")
        require(all(os.environ.get(name) == "1" for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")),
                "set client thread limits before interpreter/import startup")
        signal.signal(signal.SIGALRM, deadline)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, interrupted)
        os.environ.update(PYTHONDONTWRITEBYTECODE="1", GIT_OPTIONAL_LOCKS="0", SPARK_CONNECT_MODE_ENABLED="1",
                          SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS="900", SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS="86400",
                          SAIL_BENCHMARK_RUST_LOG="warn")
        sys.dont_write_bytecode = True
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        receipt.packages = runtime.package_versions()
        receipt.packages.update({name: importlib.metadata.version(name) for name in ("pydantic", "pydantic_core")})
        receipt.identities["python"] = {"executable": sys.executable, "version": sys.version,
                                       "client_thread_environment": {name: os.environ[name] for name in
                                           ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}}
        initial = identity(config)
        receipt.identities["before"] = initial
        prep = time.perf_counter()
        receipt.inputs_before = input_hashes(config)
        require(receipt.inputs_before == expected, "original input/oracle hash mismatch")
        for path, names, rows in ((config.vertices, ["id"], ROWS), (config.edges, ["source", "target"], EDGE_ROWS)):
            with pq.ParquetFile(path) as parquet:
                require(parquet.schema_arrow.names == names and all(field.type == pa.int64() for field in parquet.schema_arrow)
                        and parquet.metadata.num_rows == rows, "original input schema/row mismatch")
        receipt.timings["input_hash_and_footer_seconds"] = time.perf_counter() - prep
        execute(config, receipt)
        receipt.outcome = "passed"
    except BaseException as error:
        receipt.outcome = ("mismatch" if isinstance(error, Mismatch) else "nonconverged" if isinstance(error, algorithms.ConvergenceError)
                           else "timeout" if isinstance(error, TimeoutError) else "interrupted" if isinstance(error, KeyboardInterrupt) else "error")
        receipt.error = traceback.format_exc()
    finally:
        signal.alarm(0)
        try:
            receipt.inputs_after = input_hashes(config)
            require(receipt.inputs_after == expected, "input/oracle bytes changed")
            require(all(sha(Path(path)) == digest for path, digest in helpers.items()), "runner/oracle helper changed")
            if initial is not None:
                receipt.identities["after"] = identity(config)
                require(receipt.identities["after"] == initial, "source/runtime/native identity changed")
        except BaseException:
            receipt.integrity_error = traceback.format_exc()
            receipt.outcome = "integrity_error"
        counters = receipt.cgroups.get("after", {}).get("memory.events")
        if counters and int(dict(line.split() for line in counters.splitlines()).get("oom_kill", "0")):
            receipt.outcome = "oom"
        receipt.finished_utc = utc()
        (config.output / "receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n")
    print(json.dumps({"outcome": receipt.outcome, "receipt": str(config.output / "receipt.json")}))
    return 0 if receipt.outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
