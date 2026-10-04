"""Exact owner/oracle source and actual waited closure admission."""

from __future__ import annotations

import control_io as io
import control_models as m
import full_models as fm
import owner_models as o


def admit_wait(config: fm.Config, producer_pid: int) -> None:
    actual = m.GenericWait.model_validate_json(io.read(config.original_wait))
    canonical = m.CanonicalOwnerWait.model_validate_json(io.read(config.canonical_wait))
    io.require(
        actual.outcome == "passed_actual_direct_child_wait"
        and actual.returncode == 0
        and actual.wait_completed
        and actual.child_group_absent
        and actual.immutable_closure
        and not actual.forced_cleanup
        and not actual.errors
        and actual.finished_utc is not None,
        "original actual owner wait failed or incomplete",
    )
    io.require(
        actual.waiter_source_sha256 == m.GENERIC_WAIT_SHA,
        "original waiter source differs from the admitted generic wait",
    )
    io.require(
        canonical.producer == config.producer
        and canonical.original_wait == config.original_wait
        and canonical.owner_pid == actual.child_pid == producer_pid
        and canonical.owner_pgid == actual.child_pgid,
        "canonical wait must explicitly bind original child PID/PGID and producer",
    )
    io.require(
        canonical.actual_wait_completed == actual.wait_completed
        and canonical.owner_group_absent == actual.child_group_absent
        and canonical.source_unchanged == actual.immutable_closure
        and canonical.returncode == actual.returncode,
        "named canonical wait fields differ from actual original fields",
    )


def expected_target_pins(target: o.Target) -> list[o.Pin]:
    values = [
        target.python_pin,
        target.python_library,
        *target.client_files,
        target.binary,
        target.wheel,
        target.identity_helper,
        target.assembly_receipt,
        *target.provenance,
        *target.helpers.values(),
    ]
    selected = {item.path: item for item in values}
    io.require(
        all(selected[item.path] == item for item in values),
        "target declares conflicting metadata identities",
    )
    return sorted(selected.values(), key=lambda value: str(value.path))


def admit_producer(config: fm.Config, receipt: o.OwnerReceipt) -> list[o.Pin]:
    io.require(
        receipt.outcome == "completed_unqualified_closed_twohost_case"
        and receipt.immutable_closure
        and receipt.all_recorded_owned_processes_absent
        and receipt.locks_released
        and not receipt.errors
        and receipt.plan.kind == config.kind
        and receipt.plan.dataset.name == "generated-graph500-scale24",
        "positive closed current fullscale producer required",
    )
    io.require(
        o.Plan.model_validate_json(io.read(receipt.configuration)) == receipt.plan,
        "original approved configuration differs",
    )
    for target in (receipt.plan.worker1, receipt.plan.driver):
        io.require(
            {key: value.sha256 for key, value in target.helpers.items()}
            == m.OWNER_HELPER_SHA,
            "actual owner/remote/action source differs from frozen owner03",
        )
    io.require(receipt.action_receipt is not None, "actual client action required")
    action = receipt.action_receipt
    if action is None:
        raise ValueError("client action missing")
    io.require(
        action.plan == receipt.plan and action.session_closed and not action.errors,
        "actual client action configuration/session closure differs",
    )
    expected_roles = role_counts(receipt)
    io.require(
        expected_roles
        == {
            ("inspect", "morrobay"): 1,
            ("inspect", "capitola"): 1,
            ("worker", "morrobay"): 1,
            ("worker", "capitola"): 1,
            ("driver", "capitola"): 1,
            ("client", "capitola"): 1,
        },
        "six exact participant/admission records required",
    )
    pins = [receipt.configuration]
    for supervisor in receipt.supervisors:
        io.closed(supervisor.process)
    for transfer in receipt.transfers:
        io.closed(transfer)
    io.require(
        bool(receipt.transfers) and len(receipt.supervisors) == 4,
        "actual supervisor and evidence-copy waits required",
    )
    for record in receipt.host_receipts:
        target = record.request.target
        source = {"head": o.SOURCE, "tree": target.tree, "status": ""}
        io.require(
            not record.errors
            and record.source_before == record.source_after == source
            and record.pins_before == record.pins_after == expected_target_pins(target),
            "participant clean source/artifact/input client identity closure differs",
        )
        if record.request.role == "inspect":
            io.require(
                record.outcome == "passed_native_host_inspection"
                and record.host_architecture
                == record.architecture
                == target.architecture
                and record.translated is False
                and len(record.inspection_steps) == 3,
                "actual native architecture/loader inspection absent",
            )
            for inspection in record.inspection_steps:
                io.closed(inspection)
            role = "inspect-" + target.name
        else:
            io.require(
                record.outcome == "completed_closed_supervised_process"
                and record.process is not None,
                "actual supervised native process absent",
            )
            if record.process is None:
                raise ValueError("actual process missing")
            io.closed(
                record.process, native=record.request.role in ("driver", "worker")
            )
            role = (
                "worker" + str(record.request.worker_id)
                if record.request.role == "worker"
                else record.request.role
            )
            if record.request.role == "client":
                io.require(
                    record.process.pid == action.pid, "actual client action PID differs"
                )
            if record.request.role == "worker":
                env = record.request.environment
                io.require(
                    env.get("SAIL_ARGENTEA_MEMORY_BYTES") == str(16 << 30)
                    and env.get("SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE")
                    == str(32 << 30)
                    and env.get("SAIL_CLUSTER__WORKER_ID")
                    == str(record.request.worker_id),
                    "actual worker quota/pool/ID setting differs",
                )
        directory = receipt.plan.root / "closed-evidence" / role
        copied_receipt = io.pin(directory / "receipt.json")
        io.require(
            o.RemoteReceipt.model_validate_json(io.read(copied_receipt)) == record,
            "copied participant receipt differs",
        )
        pins.append(copied_receipt)
        for name, original in record.retained_files.items():
            copied = io.pin(directory / name)
            io.require(
                (copied.bytes, copied.sha256) == (original.bytes, original.sha256),
                "copied closed participant evidence differs",
            )
            pins.append(copied)
        for name in ("snapshot-before.json", "snapshot-after.json"):
            copied = io.pin(directory / name)
            snapshot = o.Snapshot.model_validate_json(io.read(copied))
            io.require(
                snapshot.recording == record
                and snapshot.all_recorded_processes_absent
                and not snapshot.processes_remaining
                and snapshot.source == source
                and snapshot.pins == record.pins_after,
                "actual current participant process/source snapshots differ",
            )
            io.require(
                (snapshot.receipt.bytes, snapshot.receipt.sha256)
                == (copied_receipt.bytes, copied_receipt.sha256),
                "current remote participant receipt identity differs from full copied bytes",
            )
            pins.append(copied)
    copied_action = receipt.plan.root / "closed-evidence/client/action-receipt.json"
    io.require(
        o.ActionReceipt.model_validate_json(io.read(io.pin(copied_action))) == action,
        "copied actual action differs",
    )
    running = {
        (r.get("worker_id"), r.get("host"), r.get("port"))
        for r in action.workers
        if r.get("status") == "RUNNING"
    }
    io.require(
        {
            (1, receipt.plan.worker1.advertise, receipt.plan.worker_ports[0]),
            (2, receipt.plan.driver.advertise, receipt.plan.worker_ports[1]),
        }
        <= running,
        "actual worker1/worker2 registrations differ",
    )
    return pins


def role_counts(receipt: o.OwnerReceipt) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for record in receipt.host_receipts:
        key = record.request.role, record.request.target.name
        result[key] = result.get(key, 0) + 1
    return result
