"""Host-local bounded X1 PID observer; never starts or signals an engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Literal

import control_models as closure_models
import darwin_memory as memory
import owner_models as closure_owner
import x1_models as x1
from pydantic import Field, model_validator

STOP_SIGNAL: int | None = None


class IdentityRefusal(ValueError):
    """The configured owned process no longer matches its identity witness."""


def utc() -> str:
    return datetime.now(UTC).isoformat()


class Watch(x1.Model):
    name: Literal["driver", "worker1", "worker2", "client"]
    receipt: Path

    @model_validator(mode="after")
    def exact_path(self) -> Watch:
        if (
            not self.receipt.is_absolute()
            or ".." in self.receipt.parts
            or self.receipt.name != "receipt.json"
            or self.receipt.parent.name != self.name
        ):
            raise ValueError("exact future host-local X1 native receipt path required")
        return self


class Config(x1.Model):
    root: Path
    host: Literal["morrobay", "capitola"]
    architecture: Literal["x86_64", "arm64"]
    watches: list[Watch] = Field(min_length=1, max_length=3)
    stop: Path
    helpers: dict[str, x1.Pin]
    interval_ms: Literal[500] = 500
    timeout_seconds: int = Field(default=21600, ge=10, le=21600)
    max_raw_bytes: Literal[134217728] = 134217728
    max_chunk_bytes: Literal[8388608] = 8388608

    @model_validator(mode="after")
    def scope(self) -> Config:
        expected = (
            {"worker1"} if self.host == "morrobay" else {"driver", "worker2", "client"}
        )
        names = {watch.name for watch in self.watches}
        if (
            self.architecture != ("x86_64" if self.host == "morrobay" else "arm64")
            or len(names) != len(self.watches)
            or not names <= expected
            or len({watch.receipt.parent.parent for watch in self.watches}) != 1
            or not self.root.is_absolute()
            or ".." in self.root.parts
            or self.stop != self.root / "root-stop.json"
            or set(self.helpers)
            != {
                "observe_x1.py",
                "darwin_memory.py",
                "x1_models.py",
                "control_models.py",
                "owner_models.py",
            }
            or any(
                self.root == watch.receipt.parent or self.root in watch.receipt.parents
                for watch in self.watches
            )
        ):
            raise ValueError(
                "one host's distinct owned X1 roles and separate observer root required"
            )
        return self


class RootStop(x1.Model):
    outcome: Literal["root_explicit_stop_after_closed_x1_case"]
    observed_utc: str
    case_owner_receipt: x1.Pin
    case_outer_wait: x1.Pin
    case_root_closure: x1.Pin
    all_case_owned_processes_closed: Literal[True]
    scope: Literal[
        "Root supplies the case closure; observer retains these identities without upgrading engine or historical qualification."
    ]

    @model_validator(mode="after")
    def proof_names(self) -> RootStop:
        if (
            self.case_owner_receipt.path.name != "receipt.json"
            or self.case_root_closure.path.name != "receipt.json"
            or self.case_outer_wait.path.name
            not in {"wait-receipt.json", "wait.json", "launch-receipt.json"}
        ):
            raise ValueError(
                "explicit case/wait/closure metadata names required; no credential file reads"
            )
        return self


class Binding(x1.Model):
    name: str
    native_pid: int = Field(gt=1)
    native_pgid: int = Field(gt=1)
    native_started_utc: str
    supervisor_pid: int = Field(gt=1)
    receipt_identity: x1.Pin
    process_start_abstime: int | None = None
    successful_samples: int = 0
    gaps: int = 0
    normal_waited_native_closure_observed: bool = False


class Point(x1.Model):
    observed_utc: str
    monotonic_seconds: float
    role: str
    kind: Literal["pending", "sample", "gap", "native_closed", "refused"]
    pid: int | None = None
    pgid: int | None = None
    observed_pgid_before: int | None = None
    observed_pgid_after: int | None = None
    process_start_abstime: int | None = None
    resident_size_bytes: int | None = None
    physical_footprint_bytes: int | None = None
    receipt_identity: x1.Pin | None = None
    error: str | None = None


class Receipt(x1.Model):
    outcome: Literal[
        "running", "stopped_bounded_process_observations_only", "error"
    ] = "running"
    observed_utc: str
    observer_pid: int
    configuration: x1.Pin
    config: Config
    before: list[x1.Pin] = Field(default_factory=list)
    after: list[x1.Pin] = Field(default_factory=list)
    bindings: dict[str, Binding] = Field(default_factory=dict)
    source_closed: bool = False
    root_stop: x1.Pin | None = None
    raw_chunks: list[x1.Pin] = Field(default_factory=list)
    final_native_receipts: dict[str, x1.Pin] = Field(default_factory=dict)
    sampling_rounds: int = 0
    errors: list[str] = Field(default_factory=list)
    observer_outer_wait_qualified: Literal[False] = False
    rooted_case_wait_closure_admitted_without_engine_qualification: bool = False
    PSS_or_cgroup_or_OS32_or_unique_process_sum_or_native_pool_fit: Literal[False] = (
        False
    )
    engine_or_historical_cause_qualified: Literal[False] = False
    scope: str = "Per-PID proc_pid_rusage(v0) RSS and physical footprint every500ms where observable, with first observed start_abstime baseline and subsequent reuse refusal. Source receipt started_utc is retained separately; no conversion or source start_abstime is invented. Missing/ESRCH observations stay gaps, never zero memory. Root owns engine lifecycle and actual observer outer wait."


def pin(path: Path, limit: int = 16 << 20) -> x1.Pin:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_size > limit
    ):
        raise ValueError("bounded same-UID physical metadata file required")
    raw = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("metadata changed while reading; observation is a gap")
    return x1.Pin(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(expected: x1.Pin) -> bytes:
    if pin(expected.path) != expected:
        raise ValueError("metadata identity changed")
    raw = expected.path.read_bytes()
    if len(raw) != expected.bytes or hashlib.sha256(raw).hexdigest() != expected.sha256:
        raise ValueError("metadata changed while reading")
    return raw


def save(path: Path, value: x1.Model) -> None:
    temporary = path.with_suffix(".writing")
    with temporary.open("x") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def admitted(
    config: Config, watch: Watch, value: x1.RemoteReceipt, identity: x1.Pin
) -> Binding | None:
    expected_role = "worker" if watch.name.startswith("worker") else watch.name
    expected_worker = int(watch.name[-1]) if watch.name.startswith("worker") else None
    if (
        value.request.root != watch.receipt.parent
        or value.request.role != expected_role
        or value.request.worker_id != expected_worker
        or value.request.target.name != config.host
        or value.request.target.architecture != config.architecture
        or value.architecture != config.architecture
        or value.supervisor_pid <= 1
    ):
        raise IdentityRefusal("receipt is not the configured host-local owned role")
    process = value.process
    if process is None:
        return None
    if (
        process.pid <= 1
        or process.pid != process.pgid
        or process.argv != value.request.argv
        or not process.started_utc
    ):
        raise IdentityRefusal(
            "actual new-session native child PID/PGID/argv/start proof required"
        )
    return Binding(
        name=watch.name,
        native_pid=process.pid,
        native_pgid=process.pgid,
        native_started_utc=process.started_utc,
        supervisor_pid=value.supervisor_pid,
        receipt_identity=identity,
    )


def same_binding(previous: Binding, current: Binding) -> None:
    if (
        previous.name,
        previous.native_pid,
        previous.native_pgid,
        previous.native_started_utc,
        previous.supervisor_pid,
    ) != (
        current.name,
        current.native_pid,
        current.native_pgid,
        current.native_started_utc,
        current.supervisor_pid,
    ):
        raise IdentityRefusal("owned native process identity changed")


def accept_sample(
    binding: Binding, actual_pgid: int, value: memory.Observation
) -> None:
    if actual_pgid != binding.native_pgid:
        raise IdentityRefusal("owned native process group changed")
    if value.error is not None:
        raise ValueError(value.error)
    if (
        value.process_start_abstime is None
        or value.process_start_abstime <= 0
        or value.resident_size_bytes is None
        or value.resident_size_bytes < 0
        or value.physical_footprint_bytes is None
        or value.physical_footprint_bytes < 0
    ):
        raise ValueError(
            "complete nonnegative rusage observation and start identity required"
        )
    if binding.process_start_abstime is None:
        binding.process_start_abstime = value.process_start_abstime
    elif binding.process_start_abstime != value.process_start_abstime:
        raise IdentityRefusal("PID reuse: observed process start_abstime changed")
    binding.successful_samples += 1


class Writer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.total = 0
        self.chunk_size = 0
        self.index = 0
        self.paths: list[Path] = []

    def write(self, point: Point) -> None:
        raw = (point.model_dump_json() + "\n").encode()
        if self.total + len(raw) > self.config.max_raw_bytes:
            raise ValueError("bounded raw observation byte limit exceeded")
        if not self.paths or self.chunk_size + len(raw) > self.config.max_chunk_bytes:
            self.index += 1
            self.paths.append(self.config.root / f"samples-{self.index:03d}.jsonl")
            self.paths[-1].touch(exist_ok=False)
            self.chunk_size = 0
        with self.paths[-1].open("ab") as stream:
            stream.write(raw)
            stream.flush()
        self.total += len(raw)
        self.chunk_size += len(raw)


def interrupted(signum: int, _frame: FrameType | None) -> None:
    global STOP_SIGNAL
    STOP_SIGNAL = signum


def point(watch: Watch, record: Receipt, writer: Writer, start: float) -> None:
    current_point = Point(
        observed_utc=utc(),
        monotonic_seconds=time.monotonic() - start,
        role=watch.name,
        kind="pending",
    )
    try:
        identity = pin(watch.receipt)
        value = x1.RemoteReceipt.model_validate_json(read(identity))
        current = admitted(record.config, watch, value, identity)
        current_point.receipt_identity = identity
        if current is None:
            writer.write(current_point)
            return
        if watch.name in record.bindings:
            binding = record.bindings[watch.name]
            same_binding(binding, current)
        else:
            binding = current
            record.bindings[watch.name] = binding
        current_point.pid, current_point.pgid = binding.native_pid, binding.native_pgid
        process = value.process
        if process is None:
            raise ValueError("native process vanished from owned receipt")
        if process.wait_completed:
            binding.normal_waited_native_closure_observed = (
                process.group_absent
                and not process.forced_cleanup
                and process.returncode in (0, -signal.SIGINT)
            )
            current_point.kind = "native_closed"
            current_point.process_start_abstime = binding.process_start_abstime
            if not binding.normal_waited_native_closure_observed:
                current_point.error = "native final wait/group/exit is retained but does not prove normal closure"
            writer.write(current_point)
            return
        actual_group = os.getpgid(binding.native_pid)
        observation = memory.observe(binding.native_pid)
        after_group = os.getpgid(binding.native_pid)
        current_point.observed_pgid_before = actual_group
        current_point.observed_pgid_after = after_group
        current_point.process_start_abstime = observation.process_start_abstime
        current_point.resident_size_bytes = observation.resident_size_bytes
        current_point.physical_footprint_bytes = observation.physical_footprint_bytes
        if actual_group != after_group:
            raise IdentityRefusal("native group changed across sample")
        accept_sample(binding, actual_group, observation)
        current_point.kind = "sample"
        current_point.process_start_abstime = observation.process_start_abstime
        current_point.resident_size_bytes = observation.resident_size_bytes
        current_point.physical_footprint_bytes = observation.physical_footprint_bytes
    except FileNotFoundError:
        current_point.kind = "gap"
        current_point.error = "owned native receipt not yet available"
    except ProcessLookupError:
        current_point.kind = "gap"
        current_point.error = (
            "ESRCH: owned PID absent at this observation; no zero memory is inferred"
        )
    except (OSError, ValueError) as error:
        current_point.kind = "gap"
        current_point.error = str(error)
        if isinstance(error, IdentityRefusal):
            current_point.kind = "refused"
            record.errors.append(str(error))
    if current_point.kind in ("gap", "refused") and watch.name in record.bindings:
        record.bindings[watch.name].gaps += 1
    writer.write(current_point)


def stop_admitted(config: Config, record: Receipt) -> x1.Pin:
    identity = pin(config.stop)
    stop = RootStop.model_validate_json(read(identity))
    for proof in (
        stop.case_owner_receipt,
        stop.case_outer_wait,
        stop.case_root_closure,
    ):
        if pin(proof.path) != proof:
            raise ValueError("root-supplied closed case evidence identity differs")
    owner = x1.OwnerReceipt.model_validate_json(read(stop.case_owner_receipt))
    actual = closure_models.GenericWait.model_validate_json(read(stop.case_outer_wait))
    raw_closure = json.loads(read(stop.case_root_closure))
    if not isinstance(raw_closure, dict):
        raise TypeError("root canonical closure must be an object")
    fields = closure_models.CanonicalOwnerWait.model_fields
    if not set(fields) <= set(raw_closure):
        raise ValueError("root canonical wait fields are missing")
    canonical = closure_models.CanonicalOwnerWait.model_validate_json(
        json.dumps({name: raw_closure[name] for name in fields})
    )
    case_wait_admitted(owner, actual, canonical, stop)
    for watch in config.watches:
        final_pin = pin(watch.receipt)
        final = x1.RemoteReceipt.model_validate_json(read(final_pin))
        current = admitted(config, watch, final, final_pin)
        if current is None or watch.name not in record.bindings:
            raise ValueError("watched native process was never admitted")
        same_binding(record.bindings[watch.name], current)
        if (
            final.process is None
            or not final.process.wait_completed
            or not final.process.group_absent
        ):
            raise ValueError(
                "root stop precedes watched process actual wait/group closure"
            )
        matching = [
            item
            for item in owner.host_receipts
            if item.request.root == final.request.root
            and item.request.role == final.request.role
            and item.request.target.name == config.host
            and item.request.worker_id == final.request.worker_id
        ]
        if len(matching) != 1 or matching[0].model_dump() != final.model_dump():
            raise ValueError(
                "final native receipt must match the root-waited owner's exact participant record"
            )
        record.bindings[watch.name].normal_waited_native_closure_observed = (
            not final.process.forced_cleanup
            and final.process.returncode in (0, -signal.SIGINT)
        )
        record.final_native_receipts[watch.name] = final_pin
    record.rooted_case_wait_closure_admitted_without_engine_qualification = True
    return identity


def case_wait_admitted(
    owner: x1.OwnerReceipt,
    actual: closure_models.GenericWait,
    canonical: closure_models.CanonicalOwnerWait,
    stop: RootStop,
) -> None:
    """Use the frozen qualifier02 contract; copied proof byte identity is retained."""
    if not (
        owner.outcome == "completed_unqualified_closed_twohost_case"
        and owner.immutable_closure
        and owner.all_recorded_owned_processes_absent
        and owner.locks_released
        and not owner.errors
        and actual.outcome == "passed_actual_direct_child_wait"
        and actual.returncode == 0
        and actual.wait_completed
        and actual.child_group_absent
        and actual.immutable_closure
        and not actual.forced_cleanup
        and not actual.errors
        and actual.finished_utc is not None
        and actual.waiter_source_sha256 == closure_models.GENERIC_WAIT_SHA
        and canonical.owner_pid == actual.child_pid == owner.pid
        and canonical.owner_pgid == actual.child_pgid == owner.pid
        and (canonical.producer.bytes, canonical.producer.sha256)
        == (stop.case_owner_receipt.bytes, stop.case_owner_receipt.sha256)
        and (canonical.original_wait.bytes, canonical.original_wait.sha256)
        == (stop.case_outer_wait.bytes, stop.case_outer_wait.sha256)
        and canonical.actual_wait_completed == actual.wait_completed
        and canonical.owner_group_absent == actual.child_group_absent
        and canonical.source_unchanged == actual.immutable_closure
        and canonical.returncode == actual.returncode
    ):
        raise ValueError("actual rooted owner/canonical/original wait closure failed")


def run(path: Path) -> int:
    configuration = pin(path)
    config = Config.model_validate_json(read(configuration))
    if config.root.exists() or config.root.is_symlink():
        raise ValueError("fresh observer evidence root required")
    config.root.mkdir(parents=True, exist_ok=False)
    record = Receipt(
        observed_utc=utc(),
        observer_pid=os.getpid(),
        configuration=configuration,
        config=config,
    )
    writer = Writer(config)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    start = time.monotonic()
    try:
        if platform.system() != "Darwin" or platform.machine() != config.architecture:
            raise ValueError("native host-local Darwin observer required")
        origins = {
            "observe_x1.py": Path(__file__),
            "darwin_memory.py": Path(memory.__file__),
            "x1_models.py": Path(x1.__file__),
            "control_models.py": Path(closure_models.__file__),
            "owner_models.py": Path(closure_owner.__file__),
        }
        for name, expected in config.helpers.items():
            if origins[name] != expected.path or pin(expected.path) != expected:
                raise ValueError("loaded frozen observer/model source differs")
        record.before = [configuration, *config.helpers.values()]
        save(config.root / "receipt.json", record)
        while True:
            if STOP_SIGNAL is not None:
                raise InterruptedError(
                    f"observer interrupted with signal{STOP_SIGNAL}; root explicit closed-case stop missing"
                )
            if time.monotonic() - start > config.timeout_seconds:
                raise TimeoutError(
                    "bounded observer timeout; raw observations retained"
                )
            for watch in config.watches:
                point(watch, record, writer, start)
            record.sampling_rounds += 1
            if record.errors:
                raise ValueError("owned process identity refused")
            if config.stop.exists():
                record.root_stop = stop_admitted(config, record)
                break
            next_sample = start + record.sampling_rounds * config.interval_ms / 1000
            time.sleep(max(0.0, next_sample - time.monotonic()))
        if not record.errors:
            record.outcome = "stopped_bounded_process_observations_only"
    except BaseException as error:  # noqa: BLE001 - preserve interruption/error and never control watched processes
        record.errors.append(f"{type(error).__name__}: {error}")
        record.outcome = "error"
    try:
        record.after = [pin(expected.path) for expected in record.before]
        record.source_closed = record.before == record.after
        if not record.source_closed:
            raise ValueError("observer source/configuration changed")
        record.raw_chunks = [pin(chunk) for chunk in writer.paths]
    except (OSError, ValueError) as error:
        record.errors.append(str(error))
        record.outcome = "error"
    record.observed_utc = utc()
    save(config.root / "receipt.json", record)
    return 0 if record.outcome == "stopped_bounded_process_observations_only" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().config))


if __name__ == "__main__":
    main()
