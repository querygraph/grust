"""Exact owner/oracle source and actual waited closure admission."""

from __future__ import annotations

import json

from pydantic import JsonValue

import control_io as io
import control_models as m
import oracle_models as bfs
import owner_models as o


def admit_wait(config: m.Config, producer_pid: int) -> None:
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


def admit_producer(config: m.Config, receipt: o.OwnerReceipt) -> list[o.Pin]:
    io.require(
        receipt.outcome == "completed_unqualified_closed_twohost_case"
        and receipt.immutable_closure
        and receipt.all_recorded_owned_processes_absent
        and receipt.locks_released
        and not receipt.errors
        and receipt.plan.kind == config.kind
        and receipt.plan.dataset.name == "signed-tiny",
        "positive closed current tiny/control producer required",
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
                    == str(1 << 20 if config.kind == "host-pool-refusal" else 32 << 30)
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


def ordinary_stages(rows: list[dict[str, JsonValue]]) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for row in rows:
        if (
            row.get("placement") != "Worker"
            or row.get("partitions") != 32
            or str(row.get("slot_group", "")).startswith("worker-extension:")
        ):
            continue
        job, stage, session = row.get("job_id"), row.get("stage"), row.get("session_id")
        io.require(
            type(job) is int and type(stage) is int and isinstance(session, str),
            "ordinary stage identities must retain physical types",
        )
        if (
            type(job) is not int
            or type(stage) is not int
            or not isinstance(session, str)
        ):
            raise ValueError("stage identity missing")
        io.require(
            (job, stage) not in result or result[job, stage] == session,
            "ambiguous ordinary stage/session",
        )
        result[job, stage] = session
    return result


def admit_tiny_oracle(
    config: m.Config, producer: o.OwnerReceipt, proof: m.NativeProof
) -> list[o.Pin]:
    if config.oracle is None or config.oracle_freeze is None:
        raise ValueError("direct tiny oracle02 receipt missing")
    io.require(
        config.oracle_freeze.sha256 == m.ORACLE_FREEZE_SHA,
        "exact frozen oracle02 required",
    )
    freeze = json.loads(io.read(config.oracle_freeze))
    oracle = bfs.Receipt.model_validate_json(io.read(config.oracle))
    configuration = bfs.Config.model_validate_json(
        io.read(o.Pin.model_validate(oracle.configuration.model_dump()))
    )
    io.require(
        oracle.outcome == "passed_full_undirected_BFS_certificate"
        and oracle.finished_utc is not None
        and not oracle.errors
        and oracle.failures.total() == 0
        and all(
            (
                oracle.full_domain_passed,
                oracle.all_original_edges_examined,
                oracle.parent_paths_and_minimum_parent_passed,
                oracle.all_edge_lower_bound_and_reachability_passed,
                oracle.terminal_empty_expansion_cap_passed,
                oracle.full_physical_certificate_passed,
                oracle.own_identity_closure_passed,
            )
        ),
        "full tiny physical certificate failed",
    )
    io.require(
        configuration.dataset == "tiny"
        and configuration.expected_vertices == 13
        and configuration.expected_edges == 14
        and configuration.source_id == -5
        and configuration.max_levels == 8
        and configuration.partitions == 32
        and configuration.schema_profile == "native13"
        and configuration.edge_schema_profile == "endpoints2"
        and configuration.source_contract.head == o.SOURCE,
        "tiny oracle request/source/projection differs",
    )
    io.require(
        config.producer.model_dump(mode="json")
        in [pin.model_dump(mode="json") for pin in configuration.producer_evidence],
        "direct oracle must pin this actual producer",
    )
    io.require(
        {
            name: pin.model_dump(mode="json")
            for name, pin in configuration.helpers.items()
        }
        == freeze["production_helpers"],
        "oracle configuration helper pins differ from frozen source",
    )
    io.require(
        oracle.vertex_rows == oracle.output_rows == oracle.unique_output_ids == 13
        and oracle.edge_rows == 14
        and oracle.reached == 11
        and oracle.max_distance == 7
        and oracle.computed_terminal_levels == 8
        and oracle.pins_before == oracle.pins_after
        and oracle.raw_files_before == oracle.raw_files_after
        and bool(oracle.raw_files_before)
        and oracle.raw_files_before == configuration.result.files
        and oracle.source_before == oracle.source_after,
        "full oracle cardinality/identity closure differs",
    )
    io.require(
        producer.native_execution_witness_passed
        and producer.native_execution_job_id == proof.job_id
        and producer.native_execution_session_id == proof.session_id,
        "producer native witness differs from independent task proof",
    )
    io.require(
        oracle.source_before is not None
        and oracle.source_before.head == o.SOURCE
        and oracle.source_before.tree == configuration.source_contract.tree
        and oracle.source_before.status == "",
        "actual oracle clean source differs",
    )
    for row in oracle.owners:
        actual = proof.owners[row.owner]
        io.require(
            (row.worker_id, row.pid, row.adjacency_id)
            == (actual.worker_id, actual.pid, actual.adjacency_id),
            "physical result owner differs from actual native process",
        )
    io.require(
        {row.worker_id for row in oracle.owners if row.rows} == {1, 2},
        "full tiny output must inhabit both physical workers",
    )
    io.require(
        sum(row.rows for row in oracle.owners) == 13,
        "full physical owner rows must cover the original domain",
    )
    return [o.Pin.model_validate(oracle.configuration.model_dump())]
