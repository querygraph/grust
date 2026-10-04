"""Time fresh engine children; verify identities and physical outputs outside them."""
from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any, Literal

import measurement
import output_oracle
import prepare_inputs
import runtime
from output_oracle import (
    Mismatch,
    load_bfs_reference,
    load_wcc_reference,
    sha,
    verify_bfs_output,
    verify_wcc_output,
)
from prepare_inputs import Receipt as InputReceipt
from prepare_inputs import check_pins
from pydantic import BaseModel, ConfigDict, Field

PECAN = "f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a"
HARNESS = "6ae2e43a903c2cee02da170465c922c72b76198e"
SAIL_SHA = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
GF_SHA = "b2a7fc0f077fafc158aaa8a45ac32e5f2af5b3d96b8050c348421fa79442722f"
NATIVE_SHA = "eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50"
Algorithm = Literal["wcc-randomized", "wcc-min-label", "bfs"]
Outcome = Literal["checking", "passed", "mismatch", "nonconverged", "cleanup_error",
                  "interrupted", "oom", "timeout", "error"]


class CellFailure(RuntimeError):
    def __init__(self, outcome: Outcome, message: str) -> None:
        super().__init__(message)
        self.outcome = outcome


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Literal["graphframes", "pecan"]
    algorithm: Algorithm
    mode: Literal["local", "process-cluster"]
    repo: Path
    harness_repo: Path
    support: Path
    output: Path
    inputs: Path
    references: Path
    sail_binary: Path
    graphframes_binary: Path
    timeout_seconds: int = Field(default=1500, ge=30, le=2400)
    reference_receipt_sha256: str
    support_sha256: str


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
    oracle_seconds: float | None = None
    guest_steal_fraction: float | None = None
    remaining_processes: list[ProcessRow] = Field(default_factory=list)
    remaining_after_cleanup: list[ProcessRow] = Field(default_factory=list)
    emergency_cleanup: list[str] = Field(default_factory=list)
    observer_error: str | None = None
    phases: dict[str, float] = Field(default_factory=dict)
    execution_verified: bool = False
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


def identities(config: CellConfig) -> dict[str, Any]:
    source_guard(config.repo, PECAN)
    source_guard(config.harness_repo, HARNESS)
    manifest_path = config.support / "support-manifest.json"
    require(sha(manifest_path) == config.support_sha256, "support manifest identity")
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["files_sha256"].items():
        path = config.support / name
        require(path.resolve().is_relative_to(config.support.resolve()) and not path.is_symlink()
                and sha(path) == expected, "support file identity " + name)
    modules = {module.__name__: module_identity(module, config.harness_repo / "examples/extensions/benchmarks" / name,
                                               sha(config.harness_repo / "examples/extensions/benchmarks" / name))
               for module, name in ((runtime, "runtime.py"), (measurement, "measurement.py"))}
    for module, name in ((output_oracle, "output_oracle.py"), (prepare_inputs, "prepare_inputs.py")):
        modules[module.__name__] = module_identity(module, config.support / name, manifest["files_sha256"][name])
    script = Path(__file__).resolve()
    require(script == (config.support / "supervise_cell.py").resolve()
            and sha(script) == manifest["files_sha256"]["supervise_cell.py"], "executed supervisor identity")
    modules["supervise_cell"] = {"path": str(script), "sha256": sha(script)}
    reference_path = config.references / "receipt.json"
    require(sha(reference_path) == config.reference_receipt_sha256, "reference phase receipt identity")
    reference = InputReceipt.model_validate_json(reference_path.read_text())
    require(reference.outcome == "passed", "input/reference phase did not pass")
    require(reference.originals_before is not None and reference.originals_after == reference.originals_before
            and reference.validation is not None and reference.references is not None, "incomplete reference phase")
    assert reference.originals_before is not None and reference.references is not None and reference.validation is not None
    require(reference.validation.isolated_vertex_count == 0, "cit-Patents scope requires zero isolates")
    check_pins(reference.originals_before)
    originals = [("cit-Patents-v.parquet", reference.originals_before.vertices),
                 ("cit-Patents-e.parquet", reference.originals_before.edges),
                 ("wcc-membership.i64le", reference.originals_before.wcc_membership)]
    for name, expected in originals:
        path = config.inputs / name
        require(not path.is_symlink() and path.stat().st_size == expected.bytes
                and sha(path) == expected.sha256, "input identity " + name)
    artifacts = [(config.references / "ids.i64le", reference.references.ids),
                 (config.references / "bfs-distances.i64le", reference.references.bfs_distances),
                 (config.inputs / "wcc-membership.i64le", reference.references.wcc_membership)]
    for path, expected in artifacts:
        require(expected.path == path and not path.is_symlink() and path.stat().st_size == expected.identity.bytes
                and sha(path) == expected.identity.sha256, "reference artifact identity " + str(path))
    require(sha(config.sail_binary) == SAIL_SHA and sha(config.graphframes_binary) == GF_SHA, "engine binary identity")
    native = runtime.native_package_identity()
    require(NATIVE_SHA in [h for name, h in native["files_sha256"].items() if name.endswith(".so")], "native identity")
    package = config.repo / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    return {"controller": PECAN, "harness": HARNESS, "sail_binary": SAIL_SHA,
            "graphframes_binary": GF_SHA, "native": native, "support": manifest,
            "reference_phase": reference.model_dump(mode="json"),
            "loaded_modules": modules,
            "package_files": {str(p.relative_to(package)): sha(p) for p in sorted(package.rglob("*.py"))},
            "harness_files": {n: sha(config.harness_repo / "examples/extensions/benchmarks" / n)
                              for n in ("runtime.py", "measurement.py")},
            "packages": runtime.package_versions()}


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
    if receipt.config.engine == "pecan":
        require(receipt.engine_receipt is not None, "missing Pecan engine receipt")
        assert receipt.engine_receipt is not None
        outcome = receipt.engine_receipt["outcome"]
        kinds: tuple[Outcome, ...] = ("nonconverged", "cleanup_error", "interrupted", "timeout", "error")
        for kind in kinds:
            if outcome == kind:
                raise CellFailure(kind, "Pecan engine receipt: " + outcome)
        require(outcome == "passed", "unknown Pecan engine outcome")
    require(receipt.engine_wait_completed and receipt.engine_returncode == 0, "engine did not complete with zero exit")
    require(receipt.observer_error is None, "sampler error")
    require(receipt.memory.get("execution_sampled") is True and receipt.sampled_engine_pss_rows > 0,
            "no complete engine PSS sample within execute boundary")


def command(config: CellConfig, reference: dict[str, Any]) -> list[str]:
    if config.engine == "graphframes":
        args = [str(config.graphframes_binary), "shortest-path" if config.algorithm == "bfs" else "wcc",
                "--vertices", (config.inputs / "cit-Patents-v.parquet").as_uri(),
                "--edges", (config.inputs / "cit-Patents-e.parquet").as_uri(),
                "--output", (config.output / "result").as_uri(), "--src-col-name", "source",
                "--dst-col-name", "target", "--max-memory", "30G", "--num-workers", "16",
                "--checkpoint-dir", str(config.output / "gf_workdir"), "--max-temp-file", "200G"]
        return args + (["--landmarks", str(reference["validation"]["source"])] if config.algorithm == "bfs" else ["--seed", "42"])
    engine = {"repo": str(config.repo), "harness_repo": str(config.harness_repo),
              "output": str(config.output), "vertices": str(config.inputs / "cit-Patents-v.parquet"),
              "edges": str(config.inputs / "cit-Patents-e.parquet"), "binary": str(config.sail_binary),
              "mode": config.mode, "algorithm": config.algorithm, "source": reference["validation"]["source"],
              "partitions": 16, "pool_bytes": (30 if config.mode == "local" else 10) * 2**30,
              "native_quota": 256 * 2**20}
    path = config.output / "engine-config.json"
    save(path, engine)
    return [sys.executable, "-B", str(config.support / "engine_pecan.py"), "--config", str(path)]


def actual_method(config: CellConfig) -> str:
    if config.engine == "graphframes":
        return "unweighted-forward-hops" if config.algorithm == "bfs" else "randomized-contraction"
    return {"bfs": "frontier", "wcc-randomized": "randomized", "wcc-min-label": "min_label"}[config.algorithm]


def execute(config: CellConfig, receipt: CellReceipt) -> None:
    before = time.perf_counter()
    receipt.identities_before = identities(config)
    reference = receipt.identities_before["reference_phase"]
    receipt.phases["identity_before_seconds"] = time.perf_counter() - before
    receipt.cgroups["before"] = measurement.cgroup_snapshot()
    limits = receipt.cgroups["before"]
    require(limits["cpu.max"] == "1600000 100000" and limits["memory.max"] == str(32 * 2**30)
            and limits["memory.swap.max"] == "0", "16CPU/32GiB/no-swap envelope")
    if any(memory_events(limits)[key] for key in ("oom", "oom_kill")):
        raise CellFailure("oom", "cgroup already has OOM events before engine launch")
    require(not processes(), "fresh private container contains another process")
    receipt.actual_engine_method = actual_method(config)
    receipt.command = command(config, reference)
    save(config.output / "receipt.json", receipt)
    sampler = measurement.Sampler(config.output / "memory-samples.jsonl", interval=0.1,
                                  watch={"scratch": config.output / ("staging" if config.engine == "pecan" else "gf_workdir")},
                                  directory_every=1)
    ticks = measurement.cpu_ticks()
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
            receipt.guest_steal_fraction = measurement.steal_fraction(ticks, measurement.cpu_ticks())
            receipt.cgroups["after_engine"] = measurement.cgroup_snapshot()
            receipt.memory = sampler.receipt()
            receipt.observer_error = sampler.error
            record_samples(receipt)
        except BaseException as error:  # noqa: BLE001 — retain observation failures without losing the active engine error.
            receipt.observer_error = repr(error)
            receipt.finalization_errors.append({"operation": "engine_observation", "error": repr(error)})
    if config.engine == "pecan" and (config.output / "engine-receipt.json").is_file():
        receipt.engine_receipt = json.loads((config.output / "engine-receipt.json").read_text())
    save(config.output / "receipt.json", receipt)
    engine_verdict(receipt)
    receipt.remaining_processes = processes()
    if receipt.remaining_processes:
        raise CellFailure("cleanup_error", "engine left owned processes after exit")
    oracle_start = time.perf_counter()
    if config.algorithm == "bfs":
        bfs = load_bfs_reference(config.references / "ids.i64le", reference["references"]["ids"]["identity"]["sha256"],
                                 config.references / "bfs-distances.i64le", reference["references"]["bfs_distances"]["identity"]["sha256"],
                                 reference["validation"]["vertex_rows"], reference["validation"]["maximum_id"], reference["validation"]["source"])
        receipt.correctness = verify_bfs_output(config.output / "result", bfs, config.engine).model_dump(mode="json")
    else:
        wcc = load_wcc_reference(config.inputs / "wcc-membership.i64le", reference["references"]["wcc_membership"]["identity"]["sha256"],
                                 reference["validation"]["vertex_rows"], reference["validation"]["maximum_id"])
        receipt.correctness = verify_wcc_output(config.output / "result", wcc).model_dump(mode="json")
    receipt.oracle_seconds = time.perf_counter() - oracle_start
    before = time.perf_counter()
    receipt.identities_after = identities(config)
    receipt.phases["identity_after_seconds"] = time.perf_counter() - before
    require(receipt.identities_before == receipt.identities_after, "source/helper/input/reference identity changed")
    receipt.cgroups["after_oracle"] = measurement.cgroup_snapshot()
    receipt.execution_verified = True


def classify(error: BaseException, receipt: CellReceipt) -> Outcome:
    if receipt.outer_timeout:
        return "timeout"
    if isinstance(error, CellFailure):
        return error.outcome
    if isinstance(error, Mismatch):
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
        close_remaining(receipt)
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
        path = receipt.config.output / "engine-receipt.json"
        if receipt.config.engine == "pecan" and path.is_file():
            receipt.engine_receipt = json.loads(path.read_text())
        if receipt.identities_before and not receipt.identities_after:
            receipt.identities_after = identities(receipt.config)
            require(receipt.identities_before == receipt.identities_after, "final identities changed")
    except BaseException as error:  # noqa: BLE001 — final integrity failures must downgrade a candidate verdict.
        late_error(receipt, "final_integrity", error)
    try:
        receipt.cgroups["final"] = measurement.cgroup_snapshot()
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
