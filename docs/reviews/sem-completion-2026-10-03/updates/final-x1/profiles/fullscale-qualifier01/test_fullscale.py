"""Pure metadata counterexamples; no graph payload, engine, process or SSH."""

import unittest
from copy import deepcopy
from pathlib import Path

from pydantic import JsonValue, ValidationError

import control_logs as logs
import control_models as c
import full_certificate as certificate
import full_models as m
import full_native as native
import oracle_models as bfs
import owner_models as o
import qualify_fullscale as qualifier


def pin() -> o.Pin:
    return o.Pin(path=Path("/synthetic/native.log"), bytes=0, sha256="a" * 64)


def fixture() -> tuple[
    list[c.NativeRecord],
    dict[str, object],
    list[dict[str, JsonValue]],
    list[c.TaskStatus],
]:
    """672 small metadata records and640 task statuses, never16M vertex data."""
    request: dict[str, object] = {
        "algorithm": "bfs_reference",
        "version": 3,
        "partitions": 32,
        "vertices": 16777216,
        "source": 13507776,
        "max_levels": 8,
        "operation_id": "op",
        "snapshot_id": "snap",
        "generation": 1,
    }
    records: list[c.NativeRecord] = []
    tasks: list[c.TaskStatus] = []
    stages: list[dict[str, JsonValue]] = [
        {
            "session_id": "session",
            "job_id": 38,
            "stage": s,
            "partitions": 32,
            "placement": "Worker",
            "mode": "Pipelined",
            "slot_group": "worker-extension:2",
        }
        for s in range(2, 22)
    ]
    # Ordinary64-wide input stage must stay outside native task-domain checks.
    stages.append(
        {
            "session_id": "session",
            "job_id": 38,
            "stage": 1,
            "partitions": 64,
            "placement": "Worker",
            "mode": "Pipelined",
            "slot_group": "ordinary",
        }
    )
    for owner in range(32):
        worker = 1 if owner % 2 == 0 else 2
        pid = 100 + worker
        counter = 0

        def event(
            kind: str,
            phase: int,
            *,
            owner: int = owner,
            worker: int = worker,
            pid: int = pid,
            **extras: JsonValue,
        ) -> c.NativeRecord:
            nonlocal counter
            counter += 1
            return c.NativeRecord.model_validate(
                dict(
                    protocol=3,
                    algorithm="bfs_reference",
                    operation_id="op",
                    snapshot_id="snap",
                    generation=1,
                    event=kind,
                    partition=owner,
                    worker_id=worker,
                    pid=pid,
                    adjacency_id=owner + 1,
                    job_id=38,
                    session_id="session",
                    phase=phase,
                    location=c.Location(log=pin(), line=counter, byte_offset=counter),
                    **extras,
                )
            )

        records.append(
            event(
                "init",
                0,
                mode="topology",
                levels=0,
                vertices=524288,
                frontier_edges=0,
                remaining_edges=16777216,
                frontier_vertices=int(owner == 0),
                local_reached=int(owner == 0),
            )
        )
        for phase in range(9):
            records.extend(
                [
                    event(
                        "decide",
                        phase,
                        mode="topology" if phase == 0 else "push",
                        levels=0 if phase == 0 else 7,
                    ),
                    event(
                        "apply",
                        phase,
                        mode="topology" if phase == 0 else "push",
                        levels=0 if phase == 0 else 7,
                        output_phase=phase + 1,
                    ),
                ]
            )
        records.extend(
            [
                event(
                    "result", 9, levels=7, reached=320, local_reached=10, converged=True
                ),
                event("close", 9, levels=7, local_reached=10),
            ]
        )
        for stage in range(2, 22):
            tasks.append(
                c.TaskStatus.model_validate(
                    {
                        "key": {
                            "job_id": 38,
                            "stage": stage,
                            "partition": owner,
                            "attempt": 0,
                        },
                        "worker_id": worker,
                        "status": "SUCCEEDED",
                        "location": c.Location(log=pin(), line=1, byte_offset=0),
                    }
                )
            )
    return records, request, stages, tasks


class MetadataControls(unittest.TestCase):
    def test_full_metadata_positive_and_input64_excluded(self) -> None:
        proof = native.prove(*fixture(), 320, 7)
        self.assertEqual(
            (proof.event_count, proof.successful_tasks, proof.directed_init_arcs),
            (672, 640, 536870912),
        )
        self.assertEqual(proof.worker_successes, {1: 320, 2: 320})

    def test_uneven_physical_split_is_accepted(self) -> None:
        records, request, stages, tasks = fixture()
        records = [
            row.model_copy(
                update={
                    "worker_id": 2 if row.partition == 31 else 1,
                    "pid": 102 if row.partition == 31 else 101,
                }
            )
            for row in records
        ]
        tasks = [
            row.model_copy(update={"worker_id": 2 if row.key.partition == 31 else 1})
            for row in tasks
        ]
        proof = native.prove(records, request, stages, tasks, 320, 7)
        self.assertEqual(proof.worker_successes, {1: 620, 2: 20})

    def test_ordinary64_status_skipped_before_native_key(self) -> None:
        records, _, stages, _ = fixture()
        location = c.Location(log=pin(), line=1, byte_offset=0)
        raw = [
            logs.Line(
                location,
                "worker_task_status worker_id=1 job_id=38 stage=1 partition=63 attempt=0 status=SUCCEEDED",
            ),
            logs.Line(
                location,
                "worker_task_status worker_id=1 job_id=38 stage=2 partition=0 attempt=0 status=SUCCEEDED",
            ),
        ]
        self.assertEqual(len(native.native_tasks(raw, 1, records, stages)), 1)
        with self.assertRaises(ValueError):
            native.native_tasks(raw, 2, records, stages)
        with self.assertRaises(ValidationError):
            native.native_tasks(
                [
                    logs.Line(
                        location,
                        "worker_task_status worker_id=1 job_id=38 stage=2 partition=63 attempt=0 status=SUCCEEDED",
                    )
                ],
                1,
                records,
                stages,
            )

    def test_missing_native_partition_task_refused(self) -> None:
        records, request, stages, tasks = fixture()
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks[:-1], 320, 7)

    def test_duplicate_success_refused(self) -> None:
        records, request, stages, tasks = fixture()
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, [*tasks, tasks[0]], 320, 7)

    def test_failed_native_task_refused(self) -> None:
        records, request, stages, tasks = fixture()
        tasks[0] = tasks[0].model_copy(update={"status": "FAILED"})
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_cross_worker_owner_refused(self) -> None:
        records, request, stages, tasks = fixture()
        tasks[0] = tasks[0].model_copy(update={"worker_id": 2})
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_cross_operation_refused(self) -> None:
        records, request, stages, tasks = fixture()
        records[0] = records[0].model_copy(update={"operation_id": "other"})
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_owner_incarnation_refused(self) -> None:
        records, request, stages, tasks = fixture()
        records[0] = records[0].model_copy(update={"pid": 999})
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_native_schedule_missing_refused(self) -> None:
        records, request, stages, tasks = fixture()
        with self.assertRaises(ValueError):
            native.prove(records[:-1], request, stages, tasks, 320, 7)

    def test_terminal_math_mismatch_refused(self) -> None:
        with self.assertRaises(ValueError):
            native.prove(*fixture(), 321, 7)

    def test_native_geometry_not_tiny_refused(self) -> None:
        records, request, stages, tasks = fixture()
        request["vertices"] = 13
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_boolean_numeric_protocol_refused(self) -> None:
        records, request, stages, tasks = fixture()
        request["version"] = True
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_native_wrong_total_arcs_refused(self) -> None:
        records, request, stages, tasks = fixture()
        changed = records[0].model_dump()
        changed["remaining_edges"] = 0
        records[0] = c.NativeRecord.model_validate(changed)
        with self.assertRaises(ValueError):
            native.prove(records, request, stages, tasks, 320, 7)

    def test_full_certificate_flag_failure_refused(self) -> None:
        oracle = bfs.Receipt(
            started_utc="now",
            finished_utc="then",
            configuration=bfs.Pin.model_validate_json(pin().model_dump_json()),
            outcome="passed_full_undirected_BFS_certificate",
            full_domain_passed=True,
            all_original_edges_examined=True,
            parent_paths_and_minimum_parent_passed=True,
            all_edge_lower_bound_and_reachability_passed=True,
            terminal_empty_expansion_cap_passed=True,
            full_physical_certificate_passed=True,
            own_identity_closure_passed=True,
        )
        certificate.admitted_flags(oracle)
        for name in (
            "full_domain_passed",
            "all_original_edges_examined",
            "parent_paths_and_minimum_parent_passed",
            "all_edge_lower_bound_and_reachability_passed",
            "terminal_empty_expansion_cap_passed",
            "full_physical_certificate_passed",
            "own_identity_closure_passed",
        ):
            with self.assertRaises(ValueError):
                certificate.admitted_flags(oracle.model_copy(update={name: False}))
        bad = deepcopy(oracle)
        bad.failures.minimum_parent = 1
        with self.assertRaises(ValueError):
            certificate.admitted_flags(bad)

    def test_wait_configuration_public_copy_and_cross_binding(self) -> None:
        original = o.Pin(path=Path("/remote/config.json"), bytes=2, sha256="a" * 64)
        copied = original.model_copy(update={"path": Path("/public/config.json")})
        wait = c.GenericWait(
            outcome="passed_actual_direct_child_wait",
            started_utc="before",
            finished_utc="after",
            configuration=str(original.path),
            configuration_sha256=original.sha256,
            waiter_source_sha256=c.GENERIC_WAIT_SHA,
            waiter_pid=25,
            argv=["python"],
            child_pid=20,
            child_pgid=20,
            returncode=0,
            wait_completed=True,
            child_group_absent=True,
            forced_cleanup=False,
            immutable_closure=True,
            errors=[],
            scope="synthetic metadata only",
        )
        qualifier.memory_config_binding(wait, original, copied)
        for changed in [
            wait.model_copy(update={"configuration": "/different/config.json"}),
            wait.model_copy(update={"configuration_sha256": "b" * 64}),
        ]:
            with self.assertRaises(ValueError):
                qualifier.memory_config_binding(changed, original, copied)
        with self.assertRaises(ValueError):
            qualifier.memory_config_binding(
                wait, original, copied.model_copy(update={"sha256": "b" * 64})
            )

    def test_current_wait_bool_integer_refused(self) -> None:
        raw = {
            "argv": ["python"],
            "pid": 20,
            "pgid": 20,
            "returncode": 0,
            "actual_wait_completed": True,
            "group_absent": True,
            "forced_cleanup": False,
        }
        m.DirectWait.model_validate(raw)
        for key, value in [
            ("actual_wait_completed", 1),
            ("forced_cleanup", 0),
            ("returncode", False),
            ("group_absent", False),
            ("returncode", 1),
        ]:
            with self.assertRaises(ValidationError):
                m.DirectWait.model_validate({**raw, key: value})


if __name__ == "__main__":
    unittest.main()
