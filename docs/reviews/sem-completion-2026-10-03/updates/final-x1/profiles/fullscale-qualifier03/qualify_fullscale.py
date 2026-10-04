"""Qualify only the conjunction of actually closed native and full-output proofs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import control_io as io
import control_logs as logs
import control_models as c
import full_admission as admission
import full_certificate as certificate
import full_models as m
import full_native as native
import oracle_models as bfs
import owner_models as o


def same_bytes(first: o.Pin, second: o.Pin) -> bool:
    return (first.bytes, first.sha256) == (second.bytes, second.sha256)


def memory_config_binding(
    wait: c.GenericWait,
    original: o.Pin,
    copied: o.Pin,
    wait_configuration: o.Pin,
    wrapper: m.WaitConfig,
    original_wait: o.Pin,
) -> None:
    io.require(
        same_bytes(original, copied)
        and wait.argv[-2:] == ["--config", str(original.path)],
        "actual original observer configuration bytes/argv differ",
    )
    declared = Path(wait.configuration)
    io.require(
        declared.is_absolute()
        and ".." not in declared.parts
        and wait.configuration_sha256 == wait_configuration.sha256
        and wrapper.root.is_absolute()
        and wrapper.root / "wait-receipt.json" == original_wait.path
        and wrapper.argv == wait.argv
        and wrapper.timeout_seconds > 0,
        "actual generic-wait configuration bytes/root/argv/timeout differ",
    )


def outer_absence_binding(
    proof: m.OuterCurrentClosure,
    original_wait: o.Pin,
    outer: c.GenericWait,
    binding_pin: o.Pin,
    binding: m.OuterBinding,
    flat_pin: o.Pin,
    flat: m.OuterFlat,
) -> set[int]:
    identities = {outer.waiter_pid, flat.pid}
    io.require(
        proof.original_outer_wait == original_wait == binding.original_outer_wait
        and proof.original_outer_config == binding.original_outer_configuration
        and proof.actual_source.sha256 == c.GENERIC_WAIT_SHA
        and proof.actual_source.sha256 == outer.waiter_source_sha256
        and proof.known_hosts == flat.known_hosts
        and "UserKnownHostsFile=" + str(proof.known_hosts.path) in outer.argv
        and proof.flat_actual_wait == flat_pin
        and proof.outer_original_binding == binding_pin
        and outer.waiter_pid == binding.waiter_pid
        and flat.pid
        == flat.pgid
        == binding.ssh_pid
        == binding.ssh_pgid
        == outer.child_pid
        == outer.child_pgid
        and outer.configuration == str(proof.original_outer_config.path)
        and outer.configuration_sha256 == proof.original_outer_config.sha256
        and binding.argv == outer.argv
        and len(proof.observed_ids_absent) == len(set(proof.observed_ids_absent))
        and all(pid > 1 for pid in proof.observed_ids_absent)
        and identities <= set(proof.observed_ids_absent),
        "separate actual original outer waiter/SSH absence provenance differs",
    )
    return identities


def process_coverage(
    required_pids: set[int],
    required_groups: set[int],
    observed_pids: set[int],
    observed_groups: set[int],
    original_outer_ids: set[int],
) -> None:
    io.require(
        required_pids <= observed_pids | original_outer_ids
        and required_groups <= observed_groups | original_outer_ids,
        "current observation omits known original participant/SSH processes",
    )


def unique(pins: list[o.Pin]) -> list[o.Pin]:
    result = {pin.path: pin for pin in pins}
    io.require(
        all(result[pin.path] == pin for pin in pins), "conflicting pinned metadata"
    )
    return sorted(result.values(), key=lambda pin: str(pin.path))


def current(config: m.Config, produced: o.OwnerReceipt) -> list[o.Pin]:
    record = m.Closure.model_validate_json(io.read(config.current_closure))
    cfg = m.ClosureConfig.model_validate_json(io.read(record.configuration))
    io.require(
        record.source == cfg.helpers.get("close_case.py")
        and {name: pin.sha256 for name, pin in cfg.helpers.items()}
        == {
            "close_case.py": "b0168eb3cc4fe2ce80df95e44246c6483dcf6b2a291a75b20635b931ca959316",
            "control_models.py": "e4003295bbabc01ab722d2febea6a7331ca0516ee63fc1f1f28ae0e089148752",
            "owner_models.py": c.OWNER_MODELS_SHA,
            "x1_models.py": c.OWNER_MODELS_SHA,
            "x1_io.py": c.OWNER_HELPER_SHA["x1_io.py"],
        },
        "exact frozen Positive05 source identity required",
    )
    actual = c.GenericWait.model_validate_json(io.read(config.original_wait))
    outer = c.GenericWait.model_validate_json(io.read(config.outer_wait))
    certificate.natural(actual)
    certificate.natural(outer)
    admission.admit_wait(config, produced.pid)
    binding = m.OuterBinding.model_validate_json(io.read(config.outer_binding))
    flat = m.OuterFlat.model_validate_json(io.read(cfg.outer_launch_wait))
    outer_cfg = m.WaitConfig.model_validate_json(
        io.read(binding.original_outer_configuration)
    )
    inner_cfg = m.WaitConfig.model_validate_json(io.read(cfg.wait_configuration))
    io.require(
        record.producer == cfg.producer == config.producer
        and record.original_wait == cfg.original_wait == config.original_wait
        and record.owner_pid == record.owner_pgid == produced.pid == actual.child_pid
        and not record.errors
        and not record.signals_sent
        and cfg.output == config.current_closure.path.parent
        and record.common_marker == cfg.common_marker
        and record.common_marker in record.released_markers,
        "current original producer/wait/owned-lock closure differs",
    )
    io.require(
        actual.configuration == str(cfg.wait_configuration.path)
        and actual.configuration_sha256 == cfg.wait_configuration.sha256
        and actual.argv == inner_cfg.argv
        and str(produced.configuration.path) in actual.argv
        and any(
            str(produced.plan.worker1.helpers["x1_owner.py"].path) in arg
            for arg in actual.argv
        ),
        "original inner owner/configuration/argv binding differs",
    )
    io.require(
        binding.original_outer_wait == config.outer_wait
        and binding.original_inner_wait == config.original_wait
        and binding.launch == cfg.launch
        and binding.waiter_source_sha256 == c.GENERIC_WAIT_SHA
        and binding.waiter_pid == outer.waiter_pid
        and binding.ssh_pid
        == flat.pid
        == flat.pgid
        == outer.child_pid
        == outer.child_pgid
        and outer.configuration == str(binding.original_outer_configuration.path)
        and outer.configuration_sha256 == binding.original_outer_configuration.sha256
        and binding.argv == outer.argv == outer_cfg.argv
        and outer.argv[0] == "/usr/bin/ssh",
        "original outer SSH actual-wait provenance differs",
    )
    outer_proof = m.OuterCurrentClosure.model_validate_json(
        io.read(config.original_outer_current_closure)
    )
    outer_ids = outer_absence_binding(
        outer_proof,
        config.outer_wait,
        outer,
        config.outer_binding,
        binding,
        cfg.outer_launch_wait,
        flat,
    )
    io.require(
        len(record.hosts) == 2
        and {host.host for host in record.hosts} == {"morrobay", "capitola"}
        and len(record.observer_steps) == 2,
        "both current independent host observations required",
    )
    for step in record.observer_steps:
        io.closed(step)
    targets = {"morrobay": produced.plan.worker1, "capitola": produced.plan.driver}
    for host in record.hosts:
        target = targets[host.host]
        io.require(
            host.architecture == target.architecture
            and host.source_before
            == host.source_after
            == {"head": o.SOURCE, "tree": m.TREE, "status": ""}
            and host.pins_before
            == host.pins_after
            == admission.expected_target_pins(target)
            and not host.processes_remaining,
            "current physical source/artifact/process closure differs",
        )
        needed = [
            row
            for row in produced.host_receipts
            if row.request.target.name == host.host
        ]
        pids = {row.supervisor_pid for row in needed}
        groups = set(pids)
        for row in needed:
            for process in [
                *row.inspection_steps,
                *([row.process] if row.process else []),
            ]:
                pids.add(process.pid)
                groups.add(process.pgid)
        if host.host == "morrobay":
            pids.update([produced.pid, actual.waiter_pid, outer.waiter_pid, flat.pid])
            groups.update(
                [produced.pid, actual.waiter_pid, outer.waiter_pid, flat.pgid]
            )
            for process in [
                *[r.process for r in produced.supervisors],
                *produced.transfers,
            ]:
                pids.add(process.pid)
                groups.add(process.pgid)
        process_coverage(
            pids,
            groups,
            set(host.recorded_pids),
            set(host.recorded_groups),
            outer_ids if host.host == "morrobay" else set(),
        )
    wait = c.GenericWait.model_validate_json(io.read(config.current_closure_wait))
    certificate.natural(wait)
    io.require(
        str(record.configuration.path) in wait.argv
        and any(str(record.source.path) in arg for arg in wait.argv),
        "actual closure executor/config wait differs",
    )
    required = [
        config.producer,
        config.original_wait,
        produced.configuration,
        cfg.wait_configuration,
        cfg.launch,
        cfg.outer_launch_wait,
        cfg.common_marker,
        *cfg.helpers.values(),
    ]
    io.require(
        all(pin in record.checked_local_pins for pin in required),
        "independent closure omits original local proof identities",
    )
    return [
        record.configuration,
        cfg.wait_configuration,
        cfg.launch,
        cfg.outer_launch_wait,
        cfg.common_marker,
        binding.original_outer_configuration,
        outer_proof.actual_source,
        outer_proof.known_hosts,
        record.source,
        *cfg.helpers.values(),
    ]


def memory(config: m.Config, produced: o.OwnerReceipt) -> list[o.Pin]:
    root = m.MemoryRoot.model_validate_json(io.read(config.memory_closure))
    result: list[o.Pin] = [root.actual_cap_current_observation_wait]
    certificate.command(root.actual_cap_current_observation_wait)
    for selected in config.memory:
        receipt = m.MemoryReceipt.model_validate_json(io.read(selected.receipt))
        wait = c.GenericWait.model_validate_json(io.read(selected.original_wait))
        stop = m.RootStop.model_validate_json(io.read(selected.stop))
        certificate.natural(wait)
        cfg = receipt.config
        actual_config = m.MemoryConfig.model_validate_json(
            io.read(selected.configuration)
        )
        wrapper = m.WaitConfig.model_validate_json(
            io.read(selected.original_wait_configuration)
        )
        if selected.host == "morrobay":
            original_wait = root.morrobay.original_wait
        else:
            originals = [
                pin
                for pin in root.capitola.pins
                if same_bytes(pin, selected.original_wait)
            ]
            io.require(
                len(originals) == 1, "one original Cap observer wait Pin required"
            )
            original_wait = originals[0]
        memory_config_binding(
            wait,
            receipt.configuration,
            selected.configuration,
            selected.original_wait_configuration,
            wrapper,
            original_wait,
        )
        io.require(
            actual_config == cfg
            and same_bytes(selected.configuration, receipt.configuration),
            "actual original observer wait/configuration bytes differ",
        )
        io.require(
            set(selected.helper_copies) == set(cfg.helpers)
            and all(
                same_bytes(selected.helper_copies[name], pin)
                for name, pin in cfg.helpers.items()
            ),
            "public observer source copies differ from original configured helper identities",
        )
        result.extend(
            [
                selected.configuration,
                selected.original_wait_configuration,
                *selected.helper_copies.values(),
            ]
        )
        roles = (
            {"worker1"}
            if selected.host == "morrobay"
            else {"driver", "worker2", "client"}
        )
        actual_roles = {
            (
                "worker" + str(row.request.worker_id)
                if row.request.role == "worker"
                else row.request.role
            ): row
            for row in produced.host_receipts
            if row.request.target.name == selected.host
            and row.request.role != "inspect"
        }
        io.require(
            cfg.host == selected.host
            and cfg.architecture
            == ("x86_64" if selected.host == "morrobay" else "arm64")
            and {watch.name for watch in cfg.watches}
            == set(receipt.bindings)
            == set(receipt.final_native_receipts)
            == roles
            and receipt.before == receipt.after
            and not receipt.errors
            and wait.child_pid == wait.child_pgid == receipt.observer_pid,
            "both actual native observer identities/closure differ",
        )
        io.require(
            wait.argv[-2:] == ["--config", str(receipt.configuration.path)]
            and cfg.stop == receipt.root_stop.path
            and same_bytes(receipt.root_stop, selected.stop),
            "actual observer wait/configuration/stop binding differs",
        )
        io.require(
            same_bytes(stop.case_owner_receipt, config.producer)
            and same_bytes(stop.case_outer_wait, config.original_wait)
            and same_bytes(stop.case_root_closure, config.current_closure),
            "observer RootStop does not bind current closed engine case",
        )
        io.require(
            {name: pin.sha256 for name, pin in cfg.helpers.items()}
            == {
                "control_models.py": "e4003295bbabc01ab722d2febea6a7331ca0516ee63fc1f1f28ae0e089148752",
                "darwin_memory.py": "3e1471cd02b1c6db874529d0464b6613036937a5c4537e05d8725cf3e232e9f3",
                "observe_x1.py": "2b21867e5889c49faeed6c555bb31f523e1bd765cb78df7507c03f0dd3262a45",
                "owner_models.py": c.OWNER_MODELS_SHA,
                "x1_models.py": c.OWNER_MODELS_SHA,
            }
            and all(
                pin in receipt.before
                for pin in [receipt.configuration, *cfg.helpers.values()]
            ),
            "unchanged observer06 configured source identity absent",
        )
        for watch in cfg.watches:
            role = actual_roles[watch.name]
            process = role.process
            if process is None:
                raise ValueError("observed actual native process absent")
            bound = receipt.bindings[watch.name]
            io.require(
                watch.receipt == role.request.root / "receipt.json"
                and (
                    bound.native_pid,
                    bound.native_pgid,
                    bound.supervisor_pid,
                    bound.native_started_utc,
                )
                == (
                    process.pid,
                    process.pgid,
                    role.supervisor_pid,
                    process.started_utc,
                ),
                "memory binding watches another native process",
            )
            copied = io.pin(
                produced.plan.root / "closed-evidence" / watch.name / "receipt.json"
            )
            io.require(
                same_bytes(receipt.final_native_receipts[watch.name], copied),
                "memory final native receipt differs from closed engine producer",
            )
        if selected.host == "morrobay":
            io.require(
                root.morrobay.producer == selected.receipt
                and root.morrobay.original_wait == selected.original_wait,
                "root current Mor memory proof differs",
            )
        else:
            io.require(
                root.capitola.producer == receipt
                and root.capitola.actual_original_wait == wait
                and any(same_bytes(pin, selected.receipt) for pin in root.capitola.pins)
                and any(
                    same_bytes(pin, selected.original_wait)
                    for pin in root.capitola.pins
                ),
                "root current Cap memory proof differs",
            )
    return result


def verify(path: Path) -> m.Audit:
    configuration = io.pin(path, 16 << 20)
    config = m.Config.model_validate_json(io.read(configuration))
    io.require(
        not config.output.exists() and not config.output.is_symlink(),
        "fresh qualification output required",
    )
    config.output.mkdir(parents=True, exist_ok=False)
    audit = m.Audit(observed_utc=io.utc(), configuration=configuration, config=config)
    try:
        modules = {
            "owner_models.py": o,
            "oracle_models.py": bfs,
            "control_models.py": c,
            "control_io.py": io,
            "control_logs.py": logs,
            "full_models.py": m,
            "full_admission.py": admission,
            "full_native.py": native,
            "full_certificate.py": certificate,
        }
        parent = Path(__file__).parent
        for name, pin in config.helpers.items():
            io.require(
                pin.path == parent / name and io.pin(pin.path) == pin,
                "actual complete helper origin/identity differs",
            )
            if name in modules:
                io.require(
                    Path(modules[name].__file__ or "") == pin.path,
                    "actual imported helper differs",
                )
        io.require(
            config.helpers["owner_models.py"].sha256 == c.OWNER_MODELS_SHA
            and config.helpers["oracle_models.py"].sha256 == c.ORACLE_MODELS_SHA,
            "copied original immutable schemas differ",
        )
        audit.pins_before = unique([configuration, *config.inputs()])
        produced = o.OwnerReceipt.model_validate_json(io.read(config.producer))
        io.require(
            config.producer.path == produced.plan.root / "receipt.json"
            and config.output != produced.plan.root
            and produced.plan.root not in config.output.parents
            and produced.plan.kind == "scale24"
            and [p.kind for p in produced.plan.prior_controls]
            == ["tiny", "bfs-cap0", "host-pool-refusal"]
            and produced.plan.driver.tree == produced.plan.worker1.tree == m.TREE,
            "actual fullscale original producer/configuration/source differs",
        )
        audit.pins_before.extend(admission.admit_producer(config, produced))
        audit.pins_before.extend(current(config, produced))
        action = produced.action_receipt
        if action is None:
            raise ValueError("actual completed full client action required")
        io.require(
            action.outcome == "completed_unqualified_bfs_export"
            and action.client_error is None
            and action.output_uri == produced.plan.output_uri
            and action.export_projection == list(bfs.NATIVE)
            and type(action.levels) is int
            and type(action.reached) is int
            and action.converged is True,
            "completed native13 export required",
        )
        oracle = bfs.Receipt.model_validate_json(io.read(config.oracle))
        workers = {
            row.request.worker_id: row
            for row in produced.host_receipts
            if row.request.role == "worker"
        }
        records: list[c.NativeRecord] = []
        tasks: list[c.TaskStatus] = []
        worker_lines: dict[int, list[logs.Line]] = {}
        for worker in (1, 2):
            row = workers[worker]
            if row.process is None:
                raise ValueError("closed physical worker PID absent")
            pin = io.pin(
                produced.plan.root / f"closed-evidence/worker{worker}/native.log"
            )
            audit.pins_before.append(pin)
            lines = list(logs.lines(pin))
            records.extend(
                logs.native_records(
                    lines,
                    cast(dict[str, object], action.native_request),
                    worker,
                    row.process.pid,
                )
            )
            worker_lines[worker] = lines
        for worker, lines in worker_lines.items():
            tasks.extend(native.native_tasks(lines, worker, records, action.stages))
        assert action.reached is not None and action.levels is not None
        proof = native.prove(
            records,
            action.native_request,
            action.stages,
            tasks,
            action.reached,
            action.levels,
        )
        io.require(
            produced.native_execution_witness_passed
            and produced.native_execution_job_id == proof.job_id
            and produced.native_execution_session_id == proof.session_id
            and len(produced.native_execution_workers) == 2
            and {row.worker_id for row in produced.native_execution_workers} == {1, 2},
            "original native witness differs from complete independent proof",
        )
        for observed in produced.native_execution_workers:
            process = workers[observed.worker_id].process
            io.require(
                process is not None
                and process.pid == observed.pid
                and observed.successful_native_tasks
                == proof.worker_successes[observed.worker_id],
                "actual native worker PID/full task counts differ",
            )
        audit.native = proof
        audit.execution_and_current_process_closure_passed = True
        audit.pins_before.extend(
            certificate.certificate(config, produced, proof, oracle)
        )
        audit.full_original_mathematical_physical_certificate_passed = True
        audit.pins_before.extend(memory(config, produced))
        audit.bounded_natural_memory_observer_closure_passed = True
        audit.pins_before = unique(audit.pins_before)
        audit.pins_after = [io.pin(pin.path) for pin in audit.pins_before]
        io.require(
            audit.pins_after == audit.pins_before,
            "closed metadata/source changed during qualification",
        )
        audit.own_metadata_identity_closure_passed = True
        audit.outcome = "passed_qualified_current_twohost_original_scale24_BFS"
    except (ValueError, OSError, KeyError, TypeError) as error:
        audit.outcome = "error"
        audit.errors.append(repr(error))
    io.save(config.output / "audit.json", audit)
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    result = verify(parser.parse_args().config)
    raise SystemExit(0 if not result.errors else 1)
