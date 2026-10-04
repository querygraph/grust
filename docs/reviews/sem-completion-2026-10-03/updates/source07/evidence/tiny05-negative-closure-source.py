"""Close retained Tiny05 client metadata admission failure; no graph verdict."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path

import close_case as q
import control_models as c
import x1_io as io
import x1_models as m


class Config(m.Model):
    case: q.Config
    executor: m.Pin
    outer_wait_configuration: m.Pin
    retained_action: m.Pin


class FailedClosure(q.Closure):
    original_failed_flags: dict[str, bool]
    original_errors: list[str]
    native_server_started: bool = True
    native_graph_algorithm_started: bool = False
    retained_action: m.Pin
    original_outer_wait: m.Pin
    original_outer_returncode: int | None = None
    original_outer_errors: list[str]
    original_outer_started_utc: str | None = None
    original_outer_finished_utc: str | None = None


def positive_pid(value: int | None) -> int:
    if type(value) is not int or value <= 1:
        raise ValueError("actual positive recorded process ID required")
    return value


def closed_proof(proof: m.ProcessProof, returncode: int) -> None:
    io.require(
        positive_pid(proof.pid) == proof.pgid
        and proof.wait_completed
        and proof.group_absent
        and proof.returncode == returncode
        and proof.finished_utc is not None
        and not proof.forced_cleanup,
        "actual naturally waited retained role exit differs",
    )


def action_shape(action: m.ActionReceipt, plan: m.Plan) -> None:
    io.require(
        action.outcome == "error"
        and action.plan == plan
        and action.errors == ["RetriesExceeded()", "stage inventory: RetriesExceeded()"]
        and action.session_closed
        and not action.workers
        and not action.stages
        and not action.native_request
        and action.levels is None
        and action.reached is None
        and action.converged is None
        and not action.export_projection
        and action.output_uri is None
        and action.client_error is None
        and not action.client_error_before_teardown,
        "exact retained metadata-only client admission failure differs",
    )


def outer_binding(
    outer: c.GenericWait,
    outer_cfg: q.WaitConfiguration,
    config: Config,
    launch: dict[str, object],
    marker: dict[str, object],
    inner: c.GenericWait,
) -> None:
    io.require(
        outer.outcome == "error"
        and outer.returncode == 1
        and outer.wait_completed
        and outer.child_group_absent
        and outer.immutable_closure
        and not outer.forced_cleanup
        and outer.errors == ["ValueError: direct child failed or its group remains"]
        and outer.finished_utc is not None
        and outer.configuration == str(config.outer_wait_configuration.path)
        and outer.configuration_sha256 == config.outer_wait_configuration.sha256
        and outer.waiter_source_sha256 == c.GENERIC_WAIT_SHA
        and outer.argv == outer_cfg.argv
        and config.case.outer_launch_wait.path == outer_cfg.root / "wait-receipt.json"
        and positive_pid(outer.waiter_pid)
        == marker.get("outer_supervisor_pid")
        == marker.get("outer_supervisor_pgid")
        and positive_pid(outer.child_pid)
        == outer.child_pgid
        == marker.get("outer_ssh_pid")
        == marker.get("outer_ssh_pgid")
        and launch.get("outer_supervisor")
        == {"pid": outer.waiter_pid, "pgid": outer.waiter_pid}
        and launch.get("outer_wait_configuration")
        == config.outer_wait_configuration.model_dump(mode="json")
        and outer.argv[0] == "/usr/bin/ssh"
        and outer.argv[-2] == "alexy@192.168.4.63"
        and str(config.case.wait_configuration.path) in outer.argv[-1]
        and inner.errors == ["ValueError: direct child failed or its group remains"],
        "exact original retained selfSSH outer wait/configuration/owner chain differs",
    )


def failure_shape(produced: m.OwnerReceipt, plan: m.Plan) -> None:
    io.require(
        produced.plan == plan
        and plan.kind == "tiny"
        and plan.run_id == "x1-native-tiny05"
        and produced.outcome == "error"
        and produced.errors
        == ["ValueError('actual local/SSH supervisor wait/closure failed')"]
        and produced.action_receipt is None
        and not produced.native_execution_workers
        and produced.native_execution_job_id is None
        and produced.native_execution_session_id is None
        and not produced.native_execution_witness_passed
        and not produced.immutable_closure
        and not produced.all_recorded_owned_processes_absent
        and not produced.locks_released
        and len(produced.host_receipts) == 4
        and [(v.host, v.role, v.root) for v in produced.supervisors]
        == [
            ("morrobay", "inspect-morrobay", plan.root / "inspection-morrobay"),
            ("capitola", "inspect-capitola", plan.remote_root / "inspection-capitola"),
            ("capitola", "driver", plan.remote_root / "driver"),
            ("capitola", "client", plan.remote_root / "client"),
        ],
        "exact retained Tiny05 client metadata admission failure differs",
    )


def role_name(recording: m.RemoteReceipt, plan: m.Plan) -> str:
    target = recording.request.target
    name = target.name
    role = recording.request.role
    io.require(
        target == (plan.worker1 if name == "morrobay" else plan.driver)
        and recording.host
        == {"morrobay": "morrobay.local", "capitola": "Capitola.local"}[name]
        and recording.architecture == target.architecture
        and recording.request.worker_id is None
        and (
            recording.errors
            == ["ValueError('actual native exit/group closure differs')"]
            if role == "client"
            else not recording.errors
        )
        and recording.source_before == recording.source_after
        and recording.pins_before == recording.pins_after,
        "actual closed role target/source differs",
    )
    if role == "inspect":
        io.require(
            recording.request.root
            == (plan.root if name == "morrobay" else plan.remote_root)
            / ("inspection-" + name)
            and recording.process is None
            and recording.outcome == "passed_native_host_inspection"
            and len(recording.inspection_steps) == 3,
            "actual passed native inspection differs",
        )
        return "inspect-" + name
    if role == "client":
        io.require(
            name == "capitola"
            and recording.request.root == plan.remote_root / "client"
            and recording.outcome == "error"
            and not recording.inspection_steps
            and recording.process is not None,
            "actual retained failed client role differs",
        )
        assert recording.process is not None
        io.require(
            recording.process.argv == recording.request.argv
            and recording.process.returncode == 1
            and not recording.process.sigint_shutdown,
            "actual failed client exit differs",
        )
        return "client"
    io.require(
        role == "driver"
        and name == "capitola"
        and recording.request.root == plan.remote_root / "driver"
        and recording.outcome == "completed_closed_supervised_process"
        and not recording.inspection_steps
        and recording.process is not None,
        "actual closed driver role differs",
    )
    assert recording.process is not None
    io.require(
        recording.process.argv == recording.request.argv
        and recording.process.returncode == 0
        and recording.process.sigint_shutdown,
        "actual normal driver wait and owned shutdown differ",
    )
    return "driver"


def execute(path: Path) -> int:
    configuration = io.pin(path)
    config = Config.model_validate_json(io.read(configuration))
    cfg = config.case
    io.require(
        config.executor.path == Path(__file__)
        and io.pin(config.executor.path) == config.executor,
        "negative05 executor identity differs",
    )
    produced = m.OwnerReceipt.model_validate_json(io.read(cfg.producer))
    plan = m.Plan.model_validate_json(io.read(produced.configuration))
    io.fresh_root(cfg.output, plan.worker1)
    io.fresh_root(cfg.output, plan.driver)
    cfg.output.mkdir(parents=True, exist_ok=False)
    result = FailedClosure(
        observed_utc=io.utc(),
        producer=cfg.producer,
        original_wait=cfg.original_wait,
        configuration=configuration,
        source=config.executor,
        common_marker=cfg.common_marker,
        original_failed_flags={
            name: getattr(produced, name)
            for name in (
                "immutable_closure",
                "all_recorded_owned_processes_absent",
                "locks_released",
            )
        },
        original_errors=produced.errors,
        retained_action=config.retained_action,
        original_outer_wait=cfg.outer_launch_wait,
        original_outer_errors=[],
    )
    try:
        failure_shape(produced, plan)
        actual = c.GenericWait.model_validate_json(io.read(cfg.original_wait))
        wait_cfg = q.WaitConfiguration.model_validate_json(
            io.read(cfg.wait_configuration)
        )
        outer = c.GenericWait.model_validate_json(io.read(cfg.outer_launch_wait))
        outer_cfg = q.WaitConfiguration.model_validate_json(
            io.read(config.outer_wait_configuration)
        )
        action = m.ActionReceipt.model_validate_json(io.read(config.retained_action))
        action_shape(action, plan)
        result.original_outer_returncode, result.original_outer_errors = (
            outer.returncode,
            outer.errors,
        )
        result.original_outer_started_utc, result.original_outer_finished_utc = (
            outer.started_utc,
            outer.finished_utc,
        )
        io.require(
            config.retained_action.path
            == plan.root / "closed-evidence/client/action-receipt.json",
            "exact original retained client action path required",
        )
        marker = json.loads(io.read(cfg.common_marker))
        launch = json.loads(io.read(cfg.launch))
        io.require(
            actual.outcome == "error"
            and actual.returncode == 1
            and actual.wait_completed
            and actual.child_group_absent
            and actual.immutable_closure
            and not actual.forced_cleanup
            and actual.finished_utc is not None
            and actual.child_pid == actual.child_pgid == produced.pid
            and actual.waiter_source_sha256 == c.GENERIC_WAIT_SHA
            and actual.configuration == str(cfg.wait_configuration.path)
            and actual.configuration_sha256 == cfg.wait_configuration.sha256
            and actual.argv == wait_cfg.argv
            and actual.argv[-2:] == ["--plan", str(produced.configuration.path)]
            and cfg.original_wait.path == wait_cfg.root / "wait-receipt.json",
            "actual natural failed owner wait differs",
        )
        outer_binding(outer, outer_cfg, config, launch, marker, actual)
        io.require(
            marker["token"] == launch["root_common_token"] == cfg.common_token
            and marker["supervisor_pid"]
            == marker["supervisor_pgid"]
            == actual.waiter_pid
            and launch["supervisor"]["supervisor_pid"]
            == launch["supervisor"]["supervisor_pgid"]
            == actual.waiter_pid
            and marker["configuration"]
            == launch["configuration"]
            == produced.configuration.model_dump(mode="json")
            and marker["wait_configuration"]
            == launch["wait_configuration"]
            == cfg.wait_configuration.model_dump(mode="json")
            and launch["waiter"]["sha256"] == c.GENERIC_WAIT_SHA
            and type(marker["root_launcher_pid"]) is int
            and marker["root_launcher_pid"] > 1
            and outer.child_pid == outer.child_pgid,
            "exact archived root ownership differs",
        )
        q.current_marker(cfg.common_marker)
        local = q.unique(
            [
                configuration,
                config.executor,
                cfg.producer,
                cfg.original_wait,
                cfg.wait_configuration,
                cfg.launch,
                cfg.outer_launch_wait,
                config.outer_wait_configuration,
                config.retained_action,
                m.Pin.model_validate_json(json.dumps(launch["known_hosts"])),
                cfg.common_marker,
                produced.configuration,
                *cfg.helpers.values(),
                plan.worker1.ssh.admission,
                plan.driver.ssh.admission,
                *(
                    [plan.worker1.ssh.known_hosts]
                    if plan.worker1.ssh.known_hosts
                    else []
                ),
                plan.dataset.admissions["morrobay"],
                plan.storage_admission,
                plan.historical_missing_receipt,
            ]
        )
        pids: dict[str, set[int]] = {
            "morrobay": {
                produced.pid,
                actual.waiter_pid,
                outer.waiter_pid,
                positive_pid(outer.child_pid),
                marker["root_launcher_pid"],
            },
            "capitola": set(),
        }
        groups: dict[str, set[int]] = {
            "morrobay": {
                produced.pid,
                actual.waiter_pid,
                outer.waiter_pid,
                positive_pid(outer.child_pgid),
            },
            "capitola": set(),
        }
        for supervisor in produced.supervisors:
            closed_proof(supervisor.process, 1 if supervisor.role == "client" else 0)
        for proof in [*[v.process for v in produced.supervisors], *produced.transfers]:
            if proof not in [v.process for v in produced.supervisors]:
                q.checked(proof)
            pids["morrobay"].add(proof.pid)
            groups["morrobay"].add(proof.pgid)
        metadata: dict[str, list[m.Pin]] = {"morrobay": [], "capitola": []}
        observed_roles: list[str] = []
        for recording in produced.host_receipts:
            name = recording.request.target.name
            role = role_name(recording, plan)
            observed_roles.append(role)
            pids[name].add(recording.supervisor_pid)
            groups[name].add(recording.supervisor_pid)
            for proof in [
                *recording.inspection_steps,
                *([recording.process] if recording.process else []),
            ]:
                closed_proof(proof, 1 if role == "client" else 0)
                pids[name].add(proof.pid)
                groups[name].add(proof.pgid)
            supervisor = next(v for v in produced.supervisors if v.role == role)
            directory = plan.root / "closed-evidence" / role
            receipt_pin = io.pin(directory / "receipt.json")
            io.require(
                supervisor.receipt == receipt_pin
                and supervisor.root == recording.request.root
                and supervisor.host == name
                and m.RemoteReceipt.model_validate_json(io.read(receipt_pin))
                == recording,
                "original fetched host receipt differs from producer",
            )
            local.append(receipt_pin)
            if role == "client":
                assert recording.process is not None
                retained = recording.retained_files.get("action-receipt.json")
                io.require(
                    retained is not None
                    and action.pid == recording.process.pid
                    and (retained.bytes, retained.sha256)
                    == (config.retained_action.bytes, config.retained_action.sha256),
                    "actual failed client action PID/retained bytes binding differs",
                )
            for filename, retained in recording.retained_files.items():
                copied = io.pin(directory / filename)
                io.require(
                    (copied.bytes, copied.sha256) == (retained.bytes, retained.sha256),
                    "retained host evidence differs",
                )
                local.append(copied)
            metadata[name] += [
                m.Pin(
                    path=recording.request.root / "receipt.json",
                    bytes=receipt_pin.bytes,
                    sha256=receipt_pin.sha256,
                ),
                *recording.retained_files.values(),
            ]
        io.require(
            observed_roles
            == ["inspect-morrobay", "inspect-capitola", "driver", "client"],
            "exact four actual role order differs",
        )
        for item in local:
            io.require(io.pin(item.path) == item, "original metadata/source changed")
        for target in [plan.worker1, plan.driver]:
            io.require(
                {name: pin.sha256 for name, pin in target.helpers.items()}
                == c.OWNER_HELPER_SHA,
                "owner06 helper surface differs",
            )
            name = target.name
            host_metadata = q.unique([*metadata[name], plan.dataset.admissions[name]])
            native = [
                str(target.python),
                "-I",
                "-B",
                "-c",
                q.HOST_CODE,
                str(target.helpers["x1_io.py"].path.parent),
                target.model_dump_json(),
                json.dumps([v.model_dump(mode="json") for v in host_metadata]),
                json.dumps(sorted(pids[name])),
                json.dumps(sorted(groups[name])),
            ]
            if name == "capitola":
                ssh = target.ssh
                native = [
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
                    ssh.host,
                    shlex.join(
                        [
                            "env",
                            "-u",
                            "PYTHONHOME",
                            "-u",
                            "PYTHONPATH",
                            "DYLD_LIBRARY_PATH="
                            + str(target.python_library.path.parent),
                            *native,
                        ]
                    ),
                ]
            stdout = cfg.output / f"{name}-observer.json"
            with (
                stdout.open("xb") as out,
                (cfg.output / f"{name}-observer.stderr").open("xb") as err,
            ):
                process = subprocess.Popen(
                    native,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                proof = m.ProcessProof(
                    pid=process.pid, pgid=process.pid, argv=native, started_utc=io.utc()
                )
                result.observer_steps.append(proof)
                io.save(cfg.output / "receipt.json", result)
                # No signals on any path. Timeout retains observer IDs and locks.
                proof.returncode = process.wait(timeout=180)
                proof.wait_completed, proof.finished_utc = True, io.utc()
                proof.group_absent = io.group_absent(process.pid)
                q.checked(proof)
            observed = q.HostObservation.model_validate_json(io.read(io.pin(stdout)))
            io.require(
                observed.host == name
                and observed.source_before
                == observed.source_after
                == {"head": m.SOURCE, "tree": target.tree, "status": ""}
                and observed.pins_before == observed.pins_after
                and observed.metadata == host_metadata
                and observed.recorded_pids == sorted(pids[name])
                and observed.recorded_groups == sorted(groups[name])
                and not observed.processes_remaining,
                "current independent host closure differs",
            )
            result.hosts.append(observed)
        io.require(
            not any(
                pid in pids["morrobay"] or group in groups["morrobay"]
                for pid, group, _ in io.process_rows()
            ),
            "current case process returned",
        )
        for proof in result.observer_steps:
            io.require(io.group_absent(proof.pgid), "current observer group remains")
        for item in q.unique(local):
            io.require(
                io.pin(item.path) == item, "original metadata changed during closure"
            )
        result.checked_local_pins = q.unique(local)
        q.current_marker(cfg.common_marker)
        io.require(
            sorted(v.name for v in q.COMMON.iterdir()) == ["owner.json"],
            "unexpected common lock members",
        )
        for lock in (q.OLD / "gate.lock", q.OLD / "serial-queue.lock"):
            pin = io.pin(lock / "owner.json")
            io.require(
                sorted(v.name for v in lock.iterdir()) == ["owner.json"]
                and q.marker_matches(json.loads(io.read(pin)), produced),
                "foreign/changed old lock refused",
            )
            result.released_markers.append(pin)
        result.owner_pid = result.owner_pgid = produced.pid
        result.returncode = actual.returncode
        result.actual_wait_completed = result.owner_group_absent = (
            result.source_unchanged
        ) = True
        result.immutable_closure = result.all_recorded_owned_processes_absent = True
        io.save(cfg.output / "before-release.json", result)
        for pin in result.released_markers:
            io.require(io.pin(pin.path) == pin, "old owned marker changed")
            pin.path.unlink()
            pin.path.parent.rmdir()
        current = q.current_marker(cfg.common_marker)
        current.path.unlink()
        q.COMMON.rmdir()
        result.released_markers.append(cfg.common_marker)
        result.locks_released = all(
            not p.exists()
            for p in [q.COMMON, q.OLD / "gate.lock", q.OLD / "serial-queue.lock"]
        )
        io.require(result.locks_released, "owned locks remain")
        result.outcome = (
            "closed_failed_twohost_client_metadata_admission_before_algorithm"
        )
    except BaseException as error:  # noqa: BLE001 - preserve actual failed admission and unreleased locks
        result.outcome = "error"
        result.errors.append(repr(error))
    result.observed_utc = io.utc()
    io.save(cfg.output / "receipt.json", result)
    return 0 if not result.errors else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    raise SystemExit(execute(parser.parse_args().config))
