"""Qualify closed current two-host controls without running an engine or oracle."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import control_admission as admission
import control_io as io
import control_logs as logs
import control_models as m
import control_native as native
import oracle_models as bfs
import owner_models as o


def qualification(config: m.Config, producer: o.OwnerReceipt, audit: m.Audit) -> None:
    action = producer.action_receipt
    if action is None:
        raise ValueError("actual action absent")
    workers = native.worker_records(producer)
    worker_lines: dict[int, list[logs.Line]] = {}
    for worker, record in workers.items():
        io.require(record.process is not None, "actual worker native PID missing")
        worker_lines[worker] = list(
            logs.lines(
                io.pin(
                    producer.plan.root / f"closed-evidence/worker{worker}/native.log"
                )
            )
        )
    driver_lines = list(
        logs.lines(io.pin(producer.plan.root / "closed-evidence/driver/native.log"))
    )
    tasks = [
        status
        for worker, rows in worker_lines.items()
        for status in logs.worker_statuses(rows, worker)
    ]
    if config.kind != "host-pool-refusal":
        records = []
        for worker, record in workers.items():
            if record.process is None:
                raise ValueError("worker PID absent")
            records.extend(
                logs.native_records(
                    worker_lines[worker],
                    cast(dict[str, object], action.native_request),
                    worker,
                    record.process.pid,
                )
            )
        proof = native.prove(
            records,
            action.native_request,
            action.stages,
            tasks,
            cap=config.kind == "bfs-cap0",
        )
        audit.native = proof
        if config.kind == "tiny":
            io.require(
                action.outcome == "completed_unqualified_bfs_export"
                and action.client_error is None
                and action.levels == 8
                and action.reached == 11
                and action.converged is True
                and action.export_projection == list(bfs.NATIVE),
                "positive actual client native13 result differs",
            )
            audit.pins_before.extend(
                admission.admit_tiny_oracle(config, producer, proof)
            )
            audit.full_tiny_physical_oracle_passed = True
            audit.both_physical_workers_executed = True
            counts = {
                worker: sum(
                    t.status == "SUCCEEDED"
                    and t.worker_id == worker
                    and t.key.job_id == proof.job_id
                    and t.key.stage in proof.stages
                    for t in tasks
                )
                for worker in (1, 2)
            }
            io.require(
                len(producer.native_execution_workers) == 2
                and {row.worker_id for row in producer.native_execution_workers}
                == {1, 2},
                "producer actual worker task counters must identify both hosts",
            )
            for observed in producer.native_execution_workers:
                process = workers[observed.worker_id].process
                io.require(
                    process is not None
                    and observed.successful_native_tasks == counts[observed.worker_id]
                    and observed.pid == process.pid,
                    "producer full actual native task/PID counters differ",
                )
            audit.outcome = "passed_qualified_twohost_tiny_bfs_control"
            return
        stage_jobs = {(proof.job_id, stage): proof.session_id for stage in proof.stages}
    else:
        io.require(
            not action.native_request
            and not action.export_projection
            and all(
                "ARGENTEA_RECEIPT " not in line.text
                for rows in worker_lines.values()
                for line in rows
            ),
            "plain host control must not execute a native extension relation",
        )
        stage_jobs = admission.ordinary_stages(action.stages)
        io.require(bool(stage_jobs), "ordinary worker stage scope absent")
    io.require(
        action.outcome == "completed_expected_error_unqualified"
        and bool(action.client_error)
        and action.client_error_before_teardown,
        "actual client must observe expected error before session teardown",
    )
    selected_tasks = [t for t in tasks if (t.key.job_id, t.key.stage) in stage_jobs]
    io.require(
        {
            t.worker_id
            for t in selected_tasks
            if t.status in ("RUNNING", "SUCCEEDED", "FAILED")
        }
        == {1, 2},
        "both physical workers must execute controlled jobs",
    )
    for report in logs.failed_reports(driver_lines):
        scope = report.key.job_id, report.key.stage
        if scope not in stage_jobs:
            continue
        for status in (
            t for t in selected_tasks if t.key == report.key and t.status == "FAILED"
        ):
            worker_record = workers[status.worker_id]
            if worker_record.process is None:
                raise ValueError("actual worker PID missing")
            candidates = (
                [None]
                if audit.native is None
                else [
                    row
                    for row in audit.native.cap_failures
                    if row.partition == report.key.partition
                    and row.worker_id == status.worker_id
                ]
            )
            for cause in candidates:
                try:
                    witness = logs.failure_witness(
                        report,
                        status,
                        worker_lines[status.worker_id],
                        worker=status.worker_id,
                        pid=worker_record.process.pid,
                        session=stage_jobs[scope],
                        native=cause,
                        request=cast(dict[str, object], action.native_request),
                        native_proof=audit.native,
                    )
                except ValueError:
                    continue  # Other failed tasks may carry cancellation/transport consequences; preserve all raw logs.
                audit.witnesses.append(witness)
    io.require(
        bool(audit.witnesses),
        "no task-bound typed refusal before teardown; generic transport/startup failure does not qualify",
    )
    for witness in audit.witnesses:
        logs.driver_teardown_order(
            witness.driver_report, driver_lines, witness.session_id
        )
    audit.native_bound_ffi_cap_decoded = any(
        row.error_boundary == "datafusion_ffi_native_cap" for row in audit.witnesses
    )
    audit.rpc_common_execution_tag_preserved = all(
        row.rpc_common_execution_tag_preserved for row in audit.witnesses
    )
    audit.both_physical_workers_executed = True
    audit.outcome = (
        "passed_typed_bfs_cap_control"
        if config.kind == "bfs-cap0"
        else "passed_typed_host_pool_refusal_control"
    )


def verify(path: Path) -> m.Audit:
    configuration = io.pin(path, 16 << 20)
    config = m.Config.model_validate_json(io.read(configuration))
    io.require(
        not config.output.exists() and not config.output.is_symlink(),
        "fresh qualification output required",
    )
    config.output.mkdir(parents=True, exist_ok=False)
    audit = m.Audit(
        observed_utc=io.utc(),
        configuration=configuration,
        config=config,
        producer=config.producer,
    )
    try:
        parent = Path(__file__).parent
        for name, module in {
            "owner_models.py": o,
            "oracle_models.py": bfs,
            "control_admission.py": admission,
            "control_models.py": m,
            "control_io.py": io,
            "control_logs.py": logs,
            "control_native.py": native,
        }.items():
            io.require(
                Path(module.__file__ or "") == config.helpers[name].path,
                "actual imported helper origin differs",
            )
        io.require(
            config.helpers["owner_models.py"].sha256 == m.OWNER_MODELS_SHA
            and config.helpers["oracle_models.py"].sha256 == m.ORACLE_MODELS_SHA,
            "copied immutable public schemas differ",
        )
        for name, expected in config.helpers.items():
            io.require(
                expected.path == parent / name and io.pin(expected.path) == expected,
                "actual local helper origin/identity differs",
            )
        audit.pins_before = [
            configuration,
            config.producer,
            config.original_wait,
            config.canonical_wait,
            *config.helpers.values(),
            *(
                [config.oracle, config.oracle_freeze]
                if config.oracle is not None and config.oracle_freeze is not None
                else []
            ),
        ]
        producer = o.OwnerReceipt.model_validate_json(io.read(config.producer))
        io.require(
            config.output != producer.plan.root
            and producer.plan.root not in config.output.parents,
            "qualification output must be separate from closed producer",
        )
        audit.pins_before.extend(admission.admit_producer(config, producer))
        admission.admit_wait(config, producer.pid)
        audit.original_wait_adapter_passed = (
            audit.producer_source_process_closure_passed
        ) = True
        qualification(config, producer, audit)
        audit.pins_after = [io.pin(pin.path) for pin in audit.pins_before]
        io.require(
            audit.pins_before == audit.pins_after,
            "qualification input/helper/log identities changed",
        )
        audit.own_identity_closure_passed = True
        if config.kind != "tiny":
            cause = (
                "bfs_level_cap" if config.kind == "bfs-cap0" else "allocation_refused"
            )
            typed = o.TypedControlQualification.model_validate(
                {
                    "outcome": audit.outcome,
                    "producer": config.producer,
                    "source": o.SOURCE,
                    "task_cause": cause,
                    "both_physical_workers_executed": True,
                    "task_bound_cause_before_teardown": True,
                    "client_error_before_teardown": True,
                    "witnessed_process_closure": True,
                    "witnesses": list(
                        {
                            str(loc.log.path): loc.log
                            for witness in audit.witnesses
                            for loc in (
                                witness.execution,
                                witness.task_failure,
                                witness.driver_report,
                            )
                        }.values()
                    )
                    + [config.original_wait, config.canonical_wait],
                    "errors": [],
                }
            )
            io.save(config.output / "qualification.json", typed)
            audit.qualification = io.pin(config.output / "qualification.json")
    except (OSError, ValueError, TypeError, KeyError) as error:
        audit.outcome = "error"
        audit.errors.append(f"{type(error).__name__}: {error}")
    audit.observed_utc = io.utc()
    io.save(config.output / "audit.json", audit)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    value = verify(parser.parse_args().config)
    raise SystemExit(1 if value.outcome == "error" else 0)


if __name__ == "__main__":
    main()
