"""Time fresh engine children; verify identities and physical outputs outside them."""
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any, Literal, Protocol, Self, cast

import measurement
import runtime
import shape_oracle
import shape_reference
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shape_reference import ReferenceReceipt, Shape, sha

PECAN = "f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a"
HARNESS = "6ae2e43a903c2cee02da170465c922c72b76198e"
SAIL_SHA = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
NATIVE_SHA = "eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50"
Variant = Literal["union", "array-explode"]
Outcome = Literal["checking", "passed", "mismatch", "nonconverged", "cleanup_error",
                  "interrupted", "oom", "timeout", "error"]


class SamplerAPI(Protocol):
    error: str | None

    def __enter__(self) -> Self: ...
    def __exit__(self, *_errors: object) -> None: ...
    def mark(self, phase: str) -> None: ...
    def receipt(self) -> dict[str, Any]: ...


class MeasurementAPI(Protocol):
    def cgroup_snapshot(self) -> dict[str, Any]: ...
    def cpu_ticks(self) -> list[int] | None: ...
    def steal_fraction(self, before: list[int] | None, after: list[int] | None) -> float | None: ...
    def Sampler(self, output: Path, *, interval: float, watch: dict[str, Path],
                directory_every: int) -> SamplerAPI: ...


class RuntimeAPI(Protocol):
    def native_package_identity(self) -> dict[str, Any]: ...
    def package_versions(self) -> dict[str, str]: ...


# Declared call boundary for the unchanged, hash-pinned external harness.
measurement_api = cast(MeasurementAPI, measurement)
runtime_api = cast(RuntimeAPI, runtime)


class CellFailure(RuntimeError):
    def __init__(self, outcome: Outcome, message: str) -> None:
        super().__init__(message)
        self.outcome = outcome


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    shape: Shape
    variant: Variant
    repo: Path
    harness_repo: Path
    support: Path
    output: Path
    vertices: Path
    edges: Path
    references: Path
    binary: Path
    timeout_seconds: int = Field(default=1500, ge=30, le=2400)
    minimum_free_bytes: int = Field(default=24 * 2**30, ge=24 * 2**30)
    reference_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    support_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def paths(self) -> CellConfig:
        for path in (self.repo, self.harness_repo, self.support, self.output, self.vertices,
                     self.edges, self.references, self.binary):
            require(path.is_absolute() and ".." not in path.parts, "absolute clean paths required")
        require(self.output.resolve() != self.references.resolve(), "separate reference and cell outputs")
        return self


class ProcessRow(BaseModel):
    pid: int
    name: str
    state: str
    starttime: int


class CellReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    config: CellConfig
    started_utc: str
    finished_utc: str | None = None
    outcome: Outcome = "checking"
    error: str | None = None
    traceback: str | None = None
    identities_before: dict[str, Any] = Field(default_factory=dict)
    identities_after: dict[str, Any] = Field(default_factory=dict)
    cgroups: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    command: list[str] = Field(default_factory=list)
    actual_engine_method: str | None = None
    dataset_scope: str = "isolated relational shape only; not a full graph algorithm"
    plans: dict[str, dict[str, Any]] = Field(default_factory=dict)
    disk_admission: dict[str, int] = Field(default_factory=dict)
    measured_boundary: str = "immediately before engine Popen through completed wait; input/output and engine lifecycle cleanup included"
    outside_boundary: str = "source/binary/helper/input/reference hashes, physical oracle, parent emergency cleanup, final integrity and ownership checks"
    launch_to_exit_seconds: float | None = None
    launch_until_interruption_seconds: float | None = None
    engine_wait_completed: bool = False
    engine_returncode: int | None = None
    engine_pid: int | None = None
    outer_timeout: bool = False
    engine_receipt: dict[str, Any] | None = None
    correctness: dict[str, Any] | None = None
    oracle_progress: shape_oracle.Progress | None = None
    oracle_seconds: float | None = None
    guest_steal_fraction: float | None = None
    remaining_processes: list[ProcessRow] = Field(default_factory=list)
    remaining_after_cleanup: list[ProcessRow] = Field(default_factory=list)
    emergency_cleanup: list[str] = Field(default_factory=list)
    observer_error: str | None = None
    phases: dict[str, float] = Field(default_factory=dict)
    execution_verified: bool = False
    ownership_admitted: bool = False
    preexisting_processes: list[ProcessRow] = Field(default_factory=list)
    final_processes: list[ProcessRow] = Field(default_factory=list)
    finalization_errors: list[dict[str, str]] = Field(default_factory=list)
    interruption_signals: list[int] = Field(default_factory=list)
    sampled_engine_pss_peak_bytes: int | None = None
    sampled_engine_rows: int = 0
    sampled_engine_pss_rows: int = 0
    memory_boundaries: dict[str, str] = Field(default_factory=lambda: {
        "sampled_engine_pss": "sum of owned engine processes during completed execute scans; supervisor and PID 1 excluded",
        "sampled_container_pss": "frozen sampler execute phase: all visible private-container processes, including supervisor",
        "after_engine_cgroup_peak": "container lifetime through engine exit, including prior identity reads and page cache",
        "final_cgroup_peak": "entire container lifetime through parent oracle and final observation; not algorithm-only",
    })
    durability_scope: str = "file fsync and atomic replace; parent-directory fsync required on Linux; macOS EINVAL/ENOTSUP tolerated without host power-loss durability qualification"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if sys.platform != "darwin" or error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(descriptor)


def save(path: Path, value: BaseModel | dict[str, Any]) -> None:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fsync_directory(path.parent)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def source_guard(repo: Path, commit: str) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, timeout=30).strip()
    require(git("rev-parse", "HEAD") == commit and not git("status", "--porcelain"), "source pin/cleanliness")
    require(subprocess.run(["git", "-C", str(repo), "symbolic-ref", "-q", "HEAD"],
                           stdout=subprocess.DEVNULL, timeout=30, check=False).returncode == 1, "source detached")


def module_identity(module: ModuleType, expected: Path, expected_sha: str) -> dict[str, str]:
    actual = Path(module.__file__ or "").resolve()
    require(actual == expected.resolve() and sha(actual) == expected_sha,
            "loaded module identity " + module.__name__)
    return {"path": str(actual), "sha256": expected_sha}


def file_identity(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "regular immutable file required: " + str(path))
    return {"bytes": path.stat().st_size, "sha256": sha(path)}


def identities(config: CellConfig) -> dict[str, Any]:
    source_guard(config.repo, PECAN)
    source_guard(config.harness_repo, HARNESS)
    manifest_path = config.support / "support-manifest.json"
    require(sha(manifest_path) == config.support_sha256, "support manifest identity")
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["files_sha256"].items():
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None, "support basename")
        require(file_identity(config.support / name)["sha256"] == expected, "support identity " + name)
    modules = {module.__name__: module_identity(module, config.harness_repo / "examples/extensions/benchmarks" / name,
                                               sha(config.harness_repo / "examples/extensions/benchmarks" / name))
               for module, name in ((runtime, "runtime.py"), (measurement, "measurement.py"))}
    for module, name in ((shape_oracle, "shape_oracle.py"), (shape_reference, "shape_reference.py")):
        modules[module.__name__] = module_identity(module, config.support / name, manifest["files_sha256"][name])
    script = Path(__file__).resolve()
    require(script == (config.support / "supervise_shape.py").resolve()
            and sha(script) == manifest["files_sha256"]["supervise_shape.py"], "executed supervisor identity")
    modules["supervise_shape"] = {"path": str(script), "sha256": sha(script)}
    reference_path = config.references / "receipt.json"
    require(sha(reference_path) == config.reference_receipt_sha256, "reference receipt identity")
    reference = ReferenceReceipt.model_validate_json(reference_path.read_text())
    require(reference.outcome == "passed" and reference.inputs_before is not None
            and reference.inputs_after == reference.inputs_before, "reference phase did not pass unchanged")
    require(reference.config.vertices == config.vertices and reference.config.edges == config.edges
            and reference.config.output == config.references, "reference/input path tuple")
    require(reference.controller_semantics == PECAN and set(reference.artifacts) == set(shape_reference.COLUMNS),
            "complete pinned shape references required")
    assert reference.inputs_before is not None
    for path, expected in ((config.vertices, reference.inputs_before.vertices), (config.edges, reference.inputs_before.edges)):
        require(file_identity(path) == expected.model_dump(mode="json"), "original input identity " + str(path))
    for name, artifact in reference.artifacts.items():
        require(artifact.file == name + ".i64le" and artifact.columns == shape_reference.COLUMNS[name], "reference artifact scope")
        require(file_identity(config.references / artifact.file) == artifact.identity.model_dump(mode="json"), "reference artifact identity")
    for name, expected in reference.helper_sha256.items():
        require(manifest["files_sha256"].get(name) == expected, "reference helper identity " + name)
    require(file_identity(config.binary)["sha256"] == SAIL_SHA, "engine binary identity")
    native = runtime_api.native_package_identity()
    require(NATIVE_SHA in [h for name, h in native["files_sha256"].items() if name.endswith(".so")], "native identity")
    package = config.repo / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    return {"controller": PECAN, "harness": HARNESS, "binary": SAIL_SHA,
            "native": native, "support": manifest, "reference_phase": reference.model_dump(mode="json"),
            "loaded_modules": modules,
            "package_files": {str(p.relative_to(package)): sha(p) for p in sorted(package.rglob("*.py"))},
            "harness_files": {n: sha(config.harness_repo / "examples/extensions/benchmarks" / n)
                              for n in ("runtime.py", "measurement.py")}, "packages": runtime_api.package_versions()}


def processes() -> list[ProcessRow]:
    result: list[ProcessRow] = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(path.name)
            if pid in (1, os.getpid()):
                continue
            raw = (path / "stat").read_text()
            tail = raw[raw.rfind(")") + 2:].split()
            if tail[0] not in ("Z", "X"):
                result.append(ProcessRow(pid=pid, name=(path / "comm").read_text().strip(),
                                         state=tail[0], starttime=int(tail[19])))
        except FileNotFoundError:
            continue
    return result


def close_remaining(receipt: CellReceipt) -> None:
    observed = processes()
    known = {(row.pid, row.starttime) for row in receipt.remaining_processes}
    receipt.remaining_processes.extend(row for row in observed if (row.pid, row.starttime) not in known)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for row in processes():
            try:
                actual = next((r for r in processes() if r.pid == row.pid), None)
                if actual is None:
                    continue
                require(actual.starttime == row.starttime, "process identity changed")
                os.kill(row.pid, sig)
                receipt.emergency_cleanup.append(f"{sig.name} pid={row.pid} starttime={row.starttime}")
            except ProcessLookupError:
                pass
            except (OSError, ValueError) as error:
                late_error(receipt, "signal_owned_process", error)
        deadline = time.monotonic() + 3
        while processes() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not processes():
            break
    receipt.remaining_after_cleanup = processes()


def memory_events(snapshot: dict[str, Any]) -> dict[str, int]:
    raw = snapshot.get("memory.events")
    require(isinstance(raw, str), "missing memory.events observation")
    assert isinstance(raw, str)
    result = {k: int(v) for k, v in (line.split() for line in raw.splitlines())}
    require("oom" in result and "oom_kill" in result, "incomplete memory.events observation")
    return result


def record_samples(receipt: CellReceipt) -> None:
    path = receipt.config.output / "memory-samples.jsonl"
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["phase"] != "execute":
                continue
            owned = [p for p in row["processes"] if p["pid"] not in (1, os.getpid())]
            if not any(p["pid"] == receipt.engine_pid for p in owned):
                continue
            receipt.sampled_engine_rows += 1
            if all(p["pss_bytes"] is not None for p in owned):
                value = sum(int(p["pss_bytes"]) for p in owned)
                receipt.sampled_engine_pss_rows += 1
                receipt.sampled_engine_pss_peak_bytes = max(receipt.sampled_engine_pss_peak_bytes or 0, value)


def engine_verdict(receipt: CellReceipt) -> None:
    if receipt.outer_timeout:
        raise CellFailure("timeout", "engine outer timeout")
    events = memory_events(receipt.cgroups["after_engine"])
    if events["oom"] or events["oom_kill"]:
        raise CellFailure("oom", "cgroup OOM events")
    require(receipt.engine_receipt is not None, "missing shape engine receipt")
    assert receipt.engine_receipt is not None
    outcome = receipt.engine_receipt["outcome"]
    kinds: tuple[Outcome, ...] = ("cleanup_error", "interrupted", "timeout", "error")
    for kind in kinds:
        if outcome == kind:
            raise CellFailure(kind, "shape engine receipt: " + outcome)
    require(outcome == "passed", "unknown shape engine outcome")
    engine = receipt.engine_receipt
    expected = json.loads((receipt.config.output / "engine-config.json").read_text())
    require(engine.get("config") == expected and engine.get("result_exported") is True
            and not engine.get("cleanup_errors") and not engine.get("staging_payload_after_shutdown")
            and engine.get("error") is None, "engine configuration/export/cleanup receipt")
    require(engine.get("controller_pin") == PECAN, "engine controller receipt")
    receipt.actual_engine_method = engine["actual_method"]
    require(receipt.engine_wait_completed and receipt.engine_returncode == 0, "engine did not complete with zero exit")
    require(receipt.observer_error is None, "sampler error")
    require(receipt.memory.get("execution_sampled") is True and receipt.sampled_engine_pss_rows > 0,
            "no complete engine PSS sample within execute boundary")


def command(config: CellConfig) -> list[str]:
    engine = {"repo": str(config.repo), "harness_repo": str(config.harness_repo),
              "output": str(config.output / "engine"), "vertices": str(config.vertices), "edges": str(config.edges),
              "binary": str(config.binary), "mode": "local", "partitions": 16,
              "pool_bytes": 30 * 2**30, "native_quota": 256 * 2**20,
              "shape": config.shape, "variant": config.variant}
    path = config.output / "engine-config.json"
    save(path, engine)
    return [sys.executable, "-B", str(config.support / "engine_shapes.py"), "--config", str(path)]


def plan_inventory(receipt: CellReceipt) -> None:
    engine = receipt.engine_receipt
    require(engine is not None and bool(engine.get("plans")), "missing raw physical plans")
    assert engine is not None
    directory = receipt.config.output / "engine"
    files = {p.name for p in directory.glob("plan-*.txt")}
    listed: set[str] = set()
    for plan in engine["plans"]:
        name = plan["file"]
        require(re.fullmatch(r"plan-[a-z0-9-]+\.txt", name) is not None and name not in listed, "plan file scope")
        listed.add(name)
        receipt.plans["engine/" + name] = {**file_identity(directory / name), "relation": plan["relation"], "scope": plan["scope"]}
    require(files == listed, "unlisted/missing physical plan")


def execute(config: CellConfig, receipt: CellReceipt) -> None:
    before = time.perf_counter()
    receipt.identities_before = identities(config)
    receipt.phases["identity_before_seconds"] = time.perf_counter() - before
    receipt.cgroups["before"] = measurement_api.cgroup_snapshot()
    limits = receipt.cgroups["before"]
    require(limits["cpu.max"] == "1600000 100000" and limits["memory.max"] == str(32 * 2**30)
            and limits["memory.swap.max"] == "0", "16CPU/32GiB/no-swap envelope")
    if any(memory_events(limits)[key] for key in ("oom", "oom_kill")):
        raise CellFailure("oom", "cgroup already has OOM events before engine launch")
    receipt.preexisting_processes = processes()
    require(not receipt.preexisting_processes, "fresh private container contains another process")
    receipt.ownership_admitted = True
    free = shutil.disk_usage(config.output).free
    receipt.disk_admission = {"free_bytes": free, "minimum_free_bytes": config.minimum_free_bytes}
    require(free >= config.minimum_free_bytes, "declared guest disk admission")
    receipt.actual_engine_method = config.shape + ":" + config.variant
    receipt.command = command(config)
    save(config.output / "receipt.json", receipt)
    sampler = measurement_api.Sampler(config.output / "memory-samples.jsonl", interval=0.1,
                                  watch={"scratch": config.output / "engine/staging"},
                                  directory_every=1)
    ticks = measurement_api.cpu_ticks()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DATAFUSION_", "GRAPHFRAMES_"))}
    env.update(RUST_LOG="warn", TOKIO_WORKER_THREADS="16", RAYON_NUM_THREADS="16",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    process: subprocess.Popen[bytes] | None = None
    try:
        with (config.output / "engine.log").open("wb") as log, sampler:
            sampler.mark("execute")
            began = time.perf_counter()
            try:
                process = subprocess.Popen(receipt.command, stdout=log, stderr=subprocess.STDOUT,
                                           cwd=config.output, env=env, start_new_session=True)
                receipt.engine_pid = process.pid
                try:
                    receipt.engine_returncode = process.wait(timeout=config.timeout_seconds)
                except subprocess.TimeoutExpired:
                    receipt.outer_timeout = True
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                    receipt.engine_returncode = process.returncode
                receipt.engine_wait_completed = True
            finally:
                elapsed = time.perf_counter() - began
                if receipt.engine_wait_completed:
                    receipt.launch_to_exit_seconds = elapsed
                else:
                    receipt.launch_until_interruption_seconds = elapsed
                sampler.mark("transition")
    finally:
        try:
            receipt.guest_steal_fraction = measurement_api.steal_fraction(ticks, measurement_api.cpu_ticks())
            receipt.cgroups["after_engine"] = measurement_api.cgroup_snapshot()
            receipt.memory = sampler.receipt()
            receipt.observer_error = sampler.error
            record_samples(receipt)
        except BaseException as error:  # noqa: BLE001 — retain observation failures without losing the active engine error.
            receipt.observer_error = repr(error)
            receipt.finalization_errors.append({"operation": "engine_observation", "error": repr(error)})
    if (config.output / "engine/engine-receipt.json").is_file():
        receipt.engine_receipt = json.loads((config.output / "engine/engine-receipt.json").read_text())
    save(config.output / "receipt.json", receipt)
    engine_verdict(receipt)
    receipt.remaining_processes = processes()
    if receipt.remaining_processes:
        raise CellFailure("cleanup_error", "engine left owned processes after exit")
    plan_inventory(receipt)
    oracle_start = time.perf_counter()
    loaded = shape_oracle.load_shape_reference(config.references, config.shape, config.reference_receipt_sha256)
    def observe(progress: shape_oracle.Progress) -> None:
        receipt.oracle_progress = progress
        save(config.output / "receipt.json", receipt)
    receipt.correctness = shape_oracle.verify_shape_output(config.output / "engine/result", loaded, config.shape,
                                                           progress=observe).model_dump(mode="json")
    receipt.oracle_seconds = time.perf_counter() - oracle_start
    before = time.perf_counter()
    receipt.identities_after = identities(config)
    receipt.phases["identity_after_seconds"] = time.perf_counter() - before
    require(receipt.identities_before == receipt.identities_after, "source/helper/input/reference identity changed")
    receipt.cgroups["after_oracle"] = measurement_api.cgroup_snapshot()
    receipt.execution_verified = True


def classify(error: BaseException, receipt: CellReceipt) -> Outcome:
    if receipt.outer_timeout:
        return "timeout"
    if isinstance(error, CellFailure):
        return error.outcome
    if isinstance(error, shape_oracle.Mismatch):
        return "mismatch"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (InterruptedError, KeyboardInterrupt)):
        return "interrupted"
    if receipt.interruption_signals:
        return "interrupted"
    return "error"


def late_error(receipt: CellReceipt, operation: str, error: BaseException) -> None:
    receipt.finalization_errors.append({"operation": operation, "error": repr(error)})
    if receipt.outcome in ("checking", "passed"):
        receipt.outcome = "cleanup_error"


def finalize(receipt: CellReceipt) -> None:
    try:
        if receipt.ownership_admitted:
            close_remaining(receipt)
        else:
            require(not processes(), "unclaimed preexisting private processes retained without signaling")
        if receipt.engine_pid is not None and not receipt.engine_wait_completed:
            try:
                pid, status = os.waitpid(receipt.engine_pid, os.WNOHANG)
                if pid == receipt.engine_pid:
                    receipt.engine_returncode = os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                pass
        require(not receipt.remaining_processes and not receipt.remaining_after_cleanup,
                "owned engine processes required emergency cleanup or remain alive")
    except BaseException as error:  # noqa: BLE001 — closure must retain interruption and uncertain ownership evidence.
        late_error(receipt, "owned_process_closure", error)
    try:
        path = receipt.config.output / "engine/engine-receipt.json"
        if path.is_file():
            receipt.engine_receipt = json.loads(path.read_text())
        if receipt.identities_before and not receipt.identities_after:
            receipt.identities_after = identities(receipt.config)
            require(receipt.identities_before == receipt.identities_after, "final identities changed")
    except BaseException as error:  # noqa: BLE001 — final integrity failures must downgrade a candidate verdict.
        late_error(receipt, "final_integrity", error)
    try:
        receipt.cgroups["final"] = measurement_api.cgroup_snapshot()
        events = memory_events(receipt.cgroups["final"])
        if events["oom"] or events["oom_kill"]:
            receipt.outcome = "oom"
        receipt.final_processes = processes()
        require(not receipt.final_processes, "owned process appeared during final observation")
    except BaseException as error:  # noqa: BLE001 — observation failure cannot leave a passing verdict.
        late_error(receipt, "final_observation", error)
    if receipt.outcome == "checking":
        receipt.outcome = "passed" if receipt.execution_verified and not receipt.finalization_errors else "error"
    receipt.finished_utc = utc()


def run_cell(config: CellConfig) -> CellReceipt:
    config.output.mkdir(parents=True, exist_ok=False)
    receipt = CellReceipt(config=config, started_utc=utc())
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    closing = False

    def interrupted(signum: int, _frame: FrameType | None) -> None:
        receipt.interruption_signals.append(signum)
        if not closing:
            raise InterruptedError(f"supervisor interrupted by signal {signum}")
        if receipt.outcome in ("checking", "passed"):
            receipt.outcome = "interrupted"

    for signum in previous:
        signal.signal(signum, interrupted)
    try:
        save(config.output / "receipt.json", receipt)
        execute(config, receipt)
    except BaseException as error:  # noqa: BLE001 — always enter owned-process closure after any engine failure.
        receipt.outcome = classify(error, receipt)
        receipt.error, receipt.traceback = repr(error), traceback.format_exc()
    finally:
        closing = True
        try:
            finalize(receipt)
            try:
                save(config.output / "receipt.json", receipt)
            except BaseException as error:
                late_error(receipt, "final_receipt_write", error)
                save(config.output / "receipt.json", receipt)
                raise
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    config = CellConfig.model_validate_json(parser.parse_args().config.read_text())
    receipt = run_cell(config)
    print(json.dumps({"outcome": receipt.outcome, "receipt": str(config.output / "receipt.json")}), flush=True)
    return 0 if receipt.outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
