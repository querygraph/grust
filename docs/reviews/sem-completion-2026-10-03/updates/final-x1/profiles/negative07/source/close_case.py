"""Current two-host source/process closure after a naturally waited X1 case."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, model_validator

import control_models as c
import x1_io as io
import x1_models as m

COMMON = Path("/tmp/morrobay-sem-completion-heavy.lock")
OLD = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
HELPERS = {"close_case.py", "x1_models.py", "x1_io.py", "control_models.py", "owner_models.py"}
HOST_CODE = """import json,os,platform,sys;sys.path.insert(0,sys.argv[1])
import x1_models as m,x1_io as io
t=m.Target.model_validate_json(sys.argv[2]);items=[m.Pin.model_validate_json(json.dumps(v)) for v in json.loads(sys.argv[3])]
pids=set(json.loads(sys.argv[4]));groups=set(json.loads(sys.argv[5]))
io.require(platform.machine()==t.architecture,'current native observer architecture differs')
before=io.identities(t);source_before=io.source(t)
for pin in items:io.require(io.pin(pin.path)==pin,'current original host metadata differs')
remaining=[list(v) for v in io.process_rows() if v[0] in pids or v[1] in groups]
source_after=io.source(t);after=io.identities(t)
for pin in items:io.require(io.pin(pin.path)==pin,'original host metadata changed')
io.require(before==after and source_before==source_after and not remaining,'current host identity/process closure differs')
print(json.dumps({'observed_utc':io.utc(),'host':t.name,'architecture':platform.machine(),'observer_pid':os.getpid(),'source_before':source_before,'source_after':source_after,'pins_before':[v.model_dump(mode='json') for v in before],'pins_after':[v.model_dump(mode='json') for v in after],'metadata':json.loads(sys.argv[3]),'recorded_pids':sorted(pids),'recorded_groups':sorted(groups),'processes_remaining':remaining}),flush=True)
"""


class Config(m.Model):
    producer: m.Pin
    original_wait: m.Pin
    wait_configuration: m.Pin
    launch: m.Pin
    outer_launch_wait: m.Pin
    common_marker: m.Pin
    common_token: str
    helpers: dict[str, m.Pin]
    output: Path

    @model_validator(mode="after")
    def contract(self) -> Config:
        if set(self.helpers) != HELPERS or any(v.path != Path(__file__).parent / name for name, v in self.helpers.items()):
            raise ValueError("exact actual closure helper set required")
        expected = {
            "x1_models.py": c.OWNER_MODELS_SHA,
            "owner_models.py": c.OWNER_MODELS_SHA,
            "x1_io.py": c.OWNER_HELPER_SHA["x1_io.py"],
            "control_models.py": "e4003295bbabc01ab722d2febea6a7331ca0516ee63fc1f1f28ae0e089148752",
        }
        if any(self.helpers[name].sha256 != sha for name, sha in expected.items()):
            raise ValueError("unchanged owner05/qualifier03 pure contracts required")
        if not self.output.is_absolute() or ".." in self.output.parts or self.common_marker.path == COMMON / "owner.json" or not self.common_token:
            raise ValueError("fresh absolute output/archived owned common marker required")
        return self


class WaitConfiguration(m.Model):
    root: Path
    argv: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(ge=30, le=43200)


class OuterLaunchWait(m.Model):
    observed_utc: str
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    returncode: Literal[0]
    actual_wait_completed: Literal[True]
    group_absent: Literal[True]
    forced_cleanup: Literal[False]
    known_hosts: m.Pin


def current_marker(expected: m.Pin) -> m.Pin:
    actual = io.pin(COMMON / "owner.json")
    io.require(
        (actual.bytes, actual.sha256) == (expected.bytes, expected.sha256),
        "current common marker differs from immutable archived ownership",
    )
    return actual


class HostObservation(m.Model):
    observed_utc: str
    host: Literal["morrobay", "capitola"]
    architecture: Literal["x86_64", "arm64"]
    observer_pid: int = Field(gt=1)
    source_before: dict[str, str]
    source_after: dict[str, str]
    pins_before: list[m.Pin]
    pins_after: list[m.Pin]
    metadata: list[m.Pin]
    recorded_pids: list[int]
    recorded_groups: list[int]
    processes_remaining: list[list[int]]


class Closure(m.Model):
    outcome: str = "checking"
    observed_utc: str
    producer: m.Pin
    original_wait: m.Pin
    configuration: m.Pin
    source: m.Pin
    owner_pid: int | None = None
    owner_pgid: int | None = None
    actual_wait_completed: bool = False
    owner_group_absent: bool = False
    source_unchanged: bool = False
    returncode: int | None = None
    all_recorded_owned_processes_absent: bool = False
    immutable_closure: bool = False
    locks_released: bool = False
    hosts: list[HostObservation] = Field(default_factory=list)
    observer_steps: list[m.ProcessProof] = Field(default_factory=list)
    checked_local_pins: list[m.Pin] = Field(default_factory=list)
    common_marker: m.Pin
    released_markers: list[m.Pin] = Field(default_factory=list)
    forced_cleanup: bool = False
    errors: list[str] = Field(default_factory=list)
    signals_sent: list[str] = Field(default_factory=list)
    engine_qualified: Literal[False] = False
    historical_cause_identified: Literal[False] = False
    scope: str = "Current original case wait, source/artifact identity, recorded process absence and exact owned lock release. Graph/math and control qualification remain separate. This executor's outer wait is root-owned and not inferred."


def unique(values: list[m.Pin]) -> list[m.Pin]:
    by_path = {value.path: value for value in values}
    io.require(all(by_path[v.path] == v for v in values), "conflicting immutable Pins")
    return sorted(by_path.values(), key=lambda value: str(value.path))


def checked(proof: m.ProcessProof) -> None:
    io.require(
        proof.pid > 1
        and proof.pgid == proof.pid
        and proof.wait_completed
        and proof.group_absent
        and proof.returncode == 0
        and proof.finished_utc is not None
        and not proof.forced_cleanup,
        "original direct process not naturally waited/closed",
    )


def marker_matches(raw: dict[str, JsonValue], produced: m.OwnerReceipt) -> bool:
    return raw == {
        "pid": produced.pid,
        "configuration": produced.configuration.model_dump(mode="json"),
        "run_id": produced.plan.run_id,
    }


def wait_binding(cfg: Config, produced: m.OwnerReceipt, actual: c.GenericWait, wait_cfg: WaitConfiguration) -> None:
    io.require(
        actual.outcome == "passed_actual_direct_child_wait"
        and actual.returncode == 0
        and actual.wait_completed
        and actual.child_group_absent
        and actual.immutable_closure
        and not actual.forced_cleanup
        and not actual.errors
        and actual.finished_utc is not None
        and actual.child_pid == actual.child_pgid == produced.pid
        and actual.waiter_source_sha256 == c.GENERIC_WAIT_SHA
        and actual.configuration == str(cfg.wait_configuration.path)
        and actual.configuration_sha256 == cfg.wait_configuration.sha256
        and actual.argv == wait_cfg.argv
        and actual.argv[-2:] == ["--plan", str(produced.configuration.path)]
        and cfg.original_wait.path == wait_cfg.root / "wait-receipt.json",
        "exact original waited owner/configuration/argv binding differs",
    )


def observe(target: m.Target, pins: list[m.Pin], pids: set[int], groups: set[int], result: Closure, output: Path) -> HostObservation:
    native = [
        str(target.python),
        "-I",
        "-B",
        "-c",
        HOST_CODE,
        str(target.helpers["x1_io.py"].path.parent),
        target.model_dump_json(),
        json.dumps([v.model_dump(mode="json") for v in pins]),
        json.dumps(sorted(pids)),
        json.dumps(sorted(groups)),
    ]
    if target.name == "morrobay":
        argv = native
    else:
        ssh = target.ssh
        io.read(ssh.admission)
        options: list[str] = []
        if ssh.known_hosts is not None:
            io.read(ssh.known_hosts)
            options = [
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=" + str(ssh.known_hosts.path),
                "-o",
                "GlobalKnownHostsFile=/dev/null",
            ]
        argv = [
            "ssh",
            "-4",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "HostKeyAlias=" + ssh.host_key_alias,
            "-i",
            str(ssh.identity_file),
            *options,
            ssh.host,
            shlex.join(
                [
                    "env",
                    "-u",
                    "PYTHONHOME",
                    "-u",
                    "PYTHONPATH",
                    "DYLD_LIBRARY_PATH=" + str(target.python_library.path.parent),
                    *native,
                ]
            ),
        ]
    stdout, stderr = output / f"{target.name}-observer.json", output / f"{target.name}-observer.stderr"
    process: subprocess.Popen[bytes] | None = None
    proof: m.ProcessProof | None = None
    try:
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            proof = m.ProcessProof(pid=process.pid, pgid=process.pid, argv=argv, started_utc=io.utc())
            result.observer_steps.append(proof)
            io.save(output / "receipt.json", result)
            proof.returncode = process.wait(timeout=180)
            proof.wait_completed, proof.finished_utc = True, io.utc()
            proof.group_absent = io.group_absent(process.pid)
            checked(proof)
    finally:
        if process is not None and proof is not None and not proof.wait_completed:
            proof.forced_cleanup = result.forced_cleanup = True
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                result.signals_sent.append(f"observer:{process.pid}:SIGTERM")
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    result.signals_sent.append(f"observer:{process.pid}:SIGKILL")
            proof.returncode = process.wait(timeout=10)
            proof.wait_completed, proof.finished_utc = True, io.utc()
            proof.group_absent = io.group_absent(process.pid)
    observed = HostObservation.model_validate_json(io.read(io.pin(stdout)))
    io.require(
        observed.host == target.name
        and observed.architecture == target.architecture
        and observed.source_before == observed.source_after == {"head": m.SOURCE, "tree": target.tree, "status": ""}
        and observed.pins_before == observed.pins_after
        and observed.metadata == pins
        and observed.recorded_pids == sorted(pids)
        and observed.recorded_groups == sorted(groups)
        and not observed.processes_remaining,
        "current independent host source/identity/process proof differs",
    )
    return observed


def execute(path: Path) -> int:
    configuration = io.pin(path)
    cfg = Config.model_validate_json(io.read(configuration))
    io.require(platform.machine() == "x86_64", "root closure runs on native Morrobay")
    produced = m.OwnerReceipt.model_validate_json(io.read(cfg.producer))
    plan = m.Plan.model_validate_json(io.read(produced.configuration))
    io.fresh_root(cfg.output, plan.worker1)
    io.fresh_root(cfg.output, plan.driver)
    cfg.output.mkdir(parents=True, exist_ok=False)
    result = Closure(
        observed_utc=io.utc(),
        producer=cfg.producer,
        original_wait=cfg.original_wait,
        configuration=configuration,
        source=io.pin(Path(__file__)),
        common_marker=cfg.common_marker,
    )
    try:
        actual = c.GenericWait.model_validate_json(io.read(cfg.original_wait))
        wait_cfg = WaitConfiguration.model_validate_json(io.read(cfg.wait_configuration))
        outer = OuterLaunchWait.model_validate_json(io.read(cfg.outer_launch_wait))
        io.require(
            produced.plan == plan
            and cfg.producer.path == plan.root / "receipt.json"
            and produced.outcome == "completed_unqualified_closed_twohost_case"
            and produced.immutable_closure
            and produced.all_recorded_owned_processes_absent
            and produced.locks_released
            and not produced.errors,
            "positive original closed owner05 case differs",
        )
        wait_binding(cfg, produced, actual, wait_cfg)
        result.owner_pid = result.owner_pgid = produced.pid
        result.returncode = actual.returncode
        marker = json.loads(io.read(cfg.common_marker))
        launch = json.loads(io.read(cfg.launch))
        io.require(
            marker["token"] == cfg.common_token
            and marker["supervisor_pid"] == marker["supervisor_pgid"] == actual.waiter_pid
            and launch["supervisor"]["supervisor_pid"] == launch["supervisor"]["supervisor_pgid"] == actual.waiter_pid
            and marker["configuration"] == launch["configuration"] == produced.configuration.model_dump(mode="json")
            and marker["wait_configuration"] == launch["wait_configuration"] == cfg.wait_configuration.model_dump(mode="json")
            and launch["waiter"]["sha256"] == c.GENERIC_WAIT_SHA
            and launch["root_common_token"] == cfg.common_token
            and type(marker["root_launcher_pid"]) is int
            and marker["root_launcher_pid"] > 1
            and outer.pid == outer.pgid,
            "exact root common/outer launch ownership differs",
        )
        current_marker(cfg.common_marker)
        for target in (plan.worker1, plan.driver):
            io.require(
                {name: pin.sha256 for name, pin in target.helpers.items()} == c.OWNER_HELPER_SHA,
                "frozen owner05 six helper byte identities differ",
            )
        local = unique(
            [
                configuration,
                cfg.producer,
                cfg.original_wait,
                cfg.wait_configuration,
                cfg.launch,
                cfg.outer_launch_wait,
                outer.known_hosts,
                cfg.common_marker,
                produced.configuration,
                *cfg.helpers.values(),
                plan.worker1.ssh.admission,
                plan.driver.ssh.admission,
                *([plan.worker1.ssh.known_hosts] if plan.worker1.ssh.known_hosts else []),
                plan.dataset.admissions["morrobay"],
                plan.historical_missing_receipt,
                plan.storage_admission,
            ]
        )
        for item in local:
            io.require(io.pin(item.path) == item, "local input/config/helper metadata changed")
        targets: dict[Literal["morrobay", "capitola"], m.Target] = {"morrobay": plan.worker1, "capitola": plan.driver}
        pids: dict[str, set[int]] = {name: set() for name in targets}
        groups: dict[str, set[int]] = {name: set() for name in targets}
        pids["morrobay"].update([produced.pid, actual.waiter_pid, outer.pid, marker["root_launcher_pid"]])
        groups["morrobay"].update([produced.pid, actual.waiter_pid, outer.pgid])
        assert actual.child_pid is not None and actual.child_pgid is not None
        for proof in [*[v.process for v in produced.supervisors], *produced.transfers]:
            checked(proof)
            pids["morrobay"].add(proof.pid)
            groups["morrobay"].add(proof.pgid)
        metadata: dict[str, list[m.Pin]] = {name: [] for name in targets}
        roles: list[tuple[str, str, int | None]] = []
        for recording in produced.host_receipts:
            name = recording.request.target.name
            io.require(
                recording.request.target == targets[name]
                and not recording.errors
                and recording.source_before == recording.source_after
                and recording.pins_before == recording.pins_after
                and recording.outcome in ("passed_native_host_inspection", "completed_closed_supervised_process"),
                "closed original host/request source differs",
            )
            roles.append((name, recording.request.role, recording.request.worker_id))
            pids[name].add(recording.supervisor_pid)
            groups[name].add(recording.supervisor_pid)
            for proof in [*recording.inspection_steps, *([recording.process] if recording.process else [])]:
                io.require(
                    proof.pid > 1
                    and proof.pgid == proof.pid
                    and proof.wait_completed
                    and proof.group_absent
                    and proof.returncode in (0, -signal.SIGINT)
                    and not proof.forced_cleanup
                    and proof.finished_utc is not None,
                    "original native role/inspection wait differs",
                )
                pids[name].add(proof.pid)
                groups[name].add(proof.pgid)
            if recording.request.role in ("driver", "worker", "client"):
                io.require(recording.process is not None, "actual native/client role PID absent")
            role = (
                f"worker{recording.request.worker_id}"
                if recording.request.role == "worker"
                else f"inspect-{name}"
                if recording.request.role == "inspect"
                else recording.request.role
            )
            directory = plan.root / "closed-evidence" / role
            receipt_pin = io.pin(directory / "receipt.json")
            io.require(
                m.RemoteReceipt.model_validate_json(io.read(receipt_pin)) == recording,
                "original fetched host receipt differs from producer",
            )
            local.append(receipt_pin)
            for filename, retained in recording.retained_files.items():
                copied = io.pin(directory / filename)
                io.require((copied.bytes, copied.sha256) == (retained.bytes, retained.sha256), "retained copied host evidence differs")
                local.append(copied)
            metadata[name] += [
                m.Pin(path=recording.request.root / "receipt.json", bytes=receipt_pin.bytes, sha256=receipt_pin.sha256),
                *recording.retained_files.values(),
            ]
        io.require(
            sorted(roles, key=str)
            == sorted(
                [
                    ("morrobay", "inspect", None),
                    ("capitola", "inspect", None),
                    ("capitola", "driver", None),
                    ("capitola", "worker", 2),
                    ("morrobay", "worker", 1),
                    ("capitola", "client", None),
                ],
                key=str,
            ),
            "complete native role/worker physical routing differs",
        )
        io.require(
            produced.action_receipt is not None and produced.action_receipt.plan == plan and produced.action_receipt.pid in pids["capitola"],
            "actual known client PID absent",
        )
        for worker in produced.native_execution_workers:
            worker_host = "morrobay" if worker.worker_id == 1 else "capitola"
            io.require(worker.pid in pids[worker_host], "actual execution worker PID absent from recorded native roles")
        for host_name, target in targets.items():
            metadata[host_name].append(plan.dataset.admissions[host_name])
            result.hosts.append(observe(target, unique(metadata[host_name]), pids[host_name], groups[host_name], result, cfg.output))
        for proof in result.observer_steps:
            checked(proof)
            io.require(io.group_absent(proof.pgid), "current owned observer group remains")
        io.require(
            not any(pid in pids["morrobay"] or group in groups["morrobay"] for pid, group, _ in io.process_rows()),
            "current local case process returned",
        )
        for item in unique(local):
            io.require(io.pin(item.path) == item, "local metadata changed during closure")
        result.checked_local_pins = unique(local)
        current_marker(cfg.common_marker)
        io.require(
            io.pin(cfg.common_marker.path) == cfg.common_marker and sorted(v.name for v in COMMON.iterdir()) == ["owner.json"],
            "common marker changed or contains extra files",
        )
        for lock in (OLD / "gate.lock", OLD / "serial-queue.lock"):
            if lock.exists():
                pin = io.pin(lock / "owner.json")
                io.require(
                    sorted(v.name for v in lock.iterdir()) == ["owner.json"] and marker_matches(json.loads(io.read(pin)), produced),
                    "foreign/changed old lock; refuse release",
                )
                result.released_markers.append(pin)
        result.actual_wait_completed = result.owner_group_absent = True
        result.source_unchanged = result.immutable_closure = result.all_recorded_owned_processes_absent = True
        io.save(cfg.output / "before-release.json", result)
        for pin in result.released_markers:
            io.require(io.pin(pin.path) == pin, "owned old marker changed before release")
            pin.path.unlink()
            pin.path.parent.rmdir()
        actual_marker = current_marker(cfg.common_marker)
        actual_marker.path.unlink()
        COMMON.rmdir()
        result.released_markers.append(cfg.common_marker)
        result.locks_released = all(not lock.exists() for lock in (COMMON, OLD / "gate.lock", OLD / "serial-queue.lock"))
        io.require(result.locks_released, "owned locks remain after release")
        canonical = c.CanonicalOwnerWait.model_validate_json(
            json.dumps({name: result.model_dump(mode="json")[name] for name in c.CanonicalOwnerWait.model_fields})
        )
        (cfg.output / "canonical-wait.json").write_text(canonical.model_dump_json(indent=2) + "\n")
        result.outcome = "passed_independent_twohost_case_closure"
    except BaseException as error:  # noqa: BLE001 - preserve failed current closure without signalling old PIDs
        result.outcome = "error"
        result.errors.append(repr(error))
    result.observed_utc = io.utc()
    io.save(cfg.output / "receipt.json", result)
    return 0 if not result.errors else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    raise SystemExit(execute(parser.parse_args().config))
