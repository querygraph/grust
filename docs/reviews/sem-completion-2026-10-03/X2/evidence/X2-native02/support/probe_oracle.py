"""Independent physical reference BFS / task-bound allocation-cause oracle.

Run after the child and owned server have exited. No Spark connection is made.
A passing induced control never diagnoses the twelve historical stream losses.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import probe_models as m
import pyarrow as pa
import pyarrow.parquet as pq
import worker_ready
from pydantic import Field, TypeAdapter

TASK = re.compile(r"job (\d+) stage (\d+) partition (\d+) attempt (\d+) execution plan")
JOB = re.compile(r"job (\d+) execution plan")
KEY = re.compile(
    r"key=TaskKey \{ job_id: JobId\((\d+)\), stage: (\d+), partition: (\d+), attempt: (\d+) \}"
)
MEMORY = re.compile(
    r"resources exhausted|failed to allocate|failed to grow.*reservation|memory.*(?:limit|exhausted)",
    re.IGNORECASE,
)


class ReferenceRow(m.Model):
    id: int
    distance: float | None
    hops: int | None
    parent: int | None


class WorkerIdentity(m.Model):
    pid: int
    pgid: int
    ppid: int
    worker_id: str
    session_id: str
    dyld_library_path: str | None
    argv: list[str]
    admitted_environment: dict[str, str]


class MemoryWitness(m.Model):
    worker_id: int
    pid: int
    log: m.Pin
    log_start: int
    log_end: int
    task_key: tuple[int, int, int, int]
    execution_failure_line: str
    task_failure_line: str
    execution_failure_precedes_task_failure: Literal[True] = True
    within_query_before_shutdown: Literal[True] = True
    global_first_fault_proven: Literal[False] = False


class Oracle(m.Model):
    outcome: Literal["passed_scoped_native_probe", "error"] = "error"
    observed_utc: str
    receipt: m.Pin
    kind: Literal["reference", "pool-refusal"]
    source_and_input_closure: bool = False
    child_server_closure: bool = False
    workers: list[WorkerIdentity] = Field(default_factory=list)
    worker_ids_executing: list[int] = Field(default_factory=list)
    job_ids: list[int] = Field(default_factory=list)
    worker_task_attempts: int = 0
    exchange_in_executed_plan: bool = False
    configured_pools_bound_to_executed_processes: bool = False
    physical_rows: int | None = None
    reachable: int | None = None
    max_hops: int | None = None
    full_schema_domain_distances_hops_parents: bool = False
    memory_witnesses: list[MemoryWitness] = Field(default_factory=list)
    observed_client_error: str | None = None
    evidence_query_errors: dict[str, str] = Field(default_factory=dict)
    retained: list[m.Pin] = Field(default_factory=list)
    full_server_phase_attribution: Literal[False] = False
    physical_memory_accounting_qualified: Literal[False] = False
    historical_original_cause: Literal["unexplained"] = "unexplained"
    errors: list[str] = Field(default_factory=list)


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("oracle requires regular files")
    return m.Pin(
        path=path,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def task_evidence(logs: dict[int, str], job_ids: set[int]) -> tuple[list[int], int]:
    owners: dict[tuple[int, ...], int] = {}
    for worker_id, raw in logs.items():
        selected = {
            tuple(int(v) for v in match.groups())
            for match in TASK.finditer(raw)
            if int(match.group(1)) in job_ids
        }
        for task in selected:
            if task in owners and owners[task] != worker_id:
                raise ValueError("same task attempt appears on different workers")
            owners[task] = worker_id
    return sorted(set(owners.values())), len(owners)


def reference_rows(fixture: Path) -> list[ReferenceRow]:
    vertices = pq.read_table(fixture / "vertices.parquet")
    edges = pq.read_table(fixture / "edges")
    if vertices.schema != pa.schema([("id", pa.int64())]) or edges.schema != pa.schema(
        [("src", pa.int64()), ("dst", pa.int64())]
    ):
        raise ValueError("original physical fixture schema differs")
    ids = vertices.column("id").to_pylist()
    if (
        len(ids) != 4096
        or any(type(v) is not int for v in ids)
        or len(set(ids)) != 4096
    ):
        raise ValueError("fixture unique original vertex domain differs")
    neighbors: dict[int, list[int]] = {vertex: [] for vertex in ids}
    for edge in edges.to_pylist():
        src, dst = edge["src"], edge["dst"]
        if src not in neighbors or dst not in neighbors:
            raise ValueError("fixture dangling edge")
        neighbors[src].append(dst)
        neighbors[dst].append(src)
    if edges.num_rows != 4097:
        raise ValueError("complete fixture edge cardinality differs")
    hops = {0: 0}
    queue = deque([0])
    while queue:
        src = queue.popleft()
        for dst in neighbors[src]:
            if dst not in hops:
                hops[dst] = hops[src] + 1
                queue.append(dst)
    result = [
        ReferenceRow(
            id=vertex,
            distance=float(hops[vertex]) if vertex in hops else None,
            hops=hops.get(vertex),
            parent=(
                0
                if vertex == 0
                else min(
                    n for n in neighbors[vertex] if hops.get(n) == hops[vertex] - 1
                )
            )
            if vertex in hops
            else None,
        )
        for vertex in sorted(ids)
    ]
    recorded = TypeAdapter(list[ReferenceRow]).validate_json(
        (fixture / "reference.json").read_bytes()
    )
    if result != recorded or len(hops) != 4095 or max(hops.values()) != 11:
        raise ValueError("independent BFS and preserved reference differ")
    return result


def verify_reference(receipt: m.Receipt, report: Oracle) -> None:
    plan = receipt.configuration
    expected = reference_rows(plan.fixture)
    result_dir = plan.output / "result"
    files = sorted(result_dir.glob("*.parquet"))
    if not files:
        raise ValueError("complete physical Parquet result missing")
    table = pq.read_table(files)
    types = {field.name: field.type for field in table.schema}
    if types != {
        "id": pa.int64(),
        "distance": pa.float64(),
        "hops": pa.int64(),
        "parent": pa.int64(),
    }:
        raise ValueError("physical reference BFS names/types differ")
    actual = TypeAdapter(list[ReferenceRow]).validate_python(table.to_pylist())
    if len(actual) != 4096 or len({row.id for row in actual}) != len(actual):
        raise ValueError("physical result row/domain cardinality differs")
    actual.sort(key=lambda row: row.id)
    if actual != expected:
        raise ValueError(
            "full original-id domain/distance/hops/rooted tight minimum-parent oracle differs"
        )
    if (
        not receipt.graph_converged
        or receipt.graph_iterations is None
        or not 1 <= receipt.graph_iterations <= 32
    ):
        raise ValueError("reference traversal did not converge within declared cap")
    if (
        receipt.graph_events is None
        or pin(receipt.graph_events.path) != receipt.graph_events
    ):
        raise ValueError("observed graph events missing or changed")
    events = TypeAdapter(list[dict[str, object]]).validate_json(
        receipt.graph_events.path.read_bytes()
    )
    plans = sorted(plan.output.glob("pre-write-step-*.txt"))
    if (
        not events
        or len(plans) != receipt.graph_iterations
        or not all(path.stat().st_size for path in plans)
    ):
        raise ValueError("full pre-write reference plan capture missing")
    report.physical_rows = len(actual)
    report.reachable = sum(row.distance is not None for row in actual)
    report.max_hops = max(row.hops for row in actual if row.hops is not None)
    report.full_schema_domain_distances_hops_parents = True


def memory_witnesses(
    raw: str,
    worker: WorkerIdentity,
    record: m.Pin,
    start: int,
    end: int,
    jobs: set[int],
) -> list[MemoryWitness]:
    """Require allocation source on task-execution hook, then matching worker report.

    One log's byte order proves its local pre-report order. Cross-process log
    timestamps are insufficient to claim the first chronological fault globally.
    """
    lines = raw.splitlines()
    result = []
    for index, line in enumerate(lines):
        match = KEY.search(line)
        if (
            "execution_failure" not in line
            or "event=task_execution_error" not in line
            or f"pid={worker.pid} " not in line
            or not MEMORY.search(line)
            or "error_chain=" not in line
            or match is None
        ):
            continue
        key = tuple(int(value) for value in match.groups())
        if len(key) != 4 or key[0] not in jobs:
            continue
        typed_key = (key[0], key[1], key[2], key[3])
        later = next(
            (
                candidate
                for candidate in lines[index + 1 :]
                if "task_failure" in candidate
                and f"pid={worker.pid} " in candidate
                and f"worker_id=Some(WorkerId({worker.worker_id}))" in candidate
                and f"session_id={worker.session_id} " in candidate
                and (other := KEY.search(candidate)) is not None
                and other.groups() == match.groups()
            ),
            None,
        )
        if later is not None:
            result.append(
                MemoryWitness(
                    worker_id=int(worker.worker_id),
                    pid=worker.pid,
                    log=record,
                    log_start=start,
                    log_end=end,
                    task_key=typed_key,
                    execution_failure_line=line,
                    task_failure_line=later,
                )
            )
    return result


def verify(path: Path, output: Path) -> Oracle:
    before = pin(path)
    receipt = m.Receipt.model_validate_json(path.read_bytes())
    plan = receipt.configuration
    report = Oracle(
        observed_utc=datetime.now(UTC).isoformat(), receipt=before, kind=plan.kind
    )
    original_pins: list[m.Pin] = []
    try:
        if (
            receipt.outcome != "completed_unqualified"
            or receipt.errors
            or not receipt.finished_utc
        ):
            raise ValueError("native child did not complete cleanly")
        if (
            not receipt.server_wait_completed
            or not receipt.shutdown_sigint
            or receipt.server_returncode not in (0, -2)
            or receipt.shutdown_sigkill
            or not receipt.server_group_absent
            or not receipt.worker_groups_absent
        ):
            raise ValueError(
                "native child/server/worker actual wait and closure incomplete"
            )
        if receipt.sampler_error or receipt.historical_original_cause != "unexplained":
            raise ValueError("observer failed or historical cause claim changed")
        report.child_server_closure = True
        if (
            receipt.inputs_before != receipt.inputs_after
            or receipt.source_before != receipt.source_after
        ):
            raise ValueError("source/input byte closure differs")
        for record in receipt.inputs_before.values():
            if pin(record.path) != record:
                raise ValueError("original/helper/client bytes changed")
        report.source_and_input_closure = True
        driver_path = plan.output / "server.log"
        driver = driver_path.read_bytes()
        bootstrap, readiness = receipt.session_bootstrap, receipt.worker_readiness
        if (
            bootstrap is None
            or not bootstrap.spark_version
            or readiness is None
            or len(readiness.worker_ids) != 2
        ):
            raise ValueError("explicit metadata bootstrap/two-worker readiness missing")
        if bootstrap.server_log_end > readiness.server_log_end:
            raise ValueError("metadata bootstrap follows readiness")
        if worker_ready.registered_ids(
            driver[: readiness.server_log_end].decode()
        ) != set(readiness.worker_ids):
            raise ValueError("pre-action worker registrations differ")
        if any(pin(record.path) != record for record in readiness.identity_files):
            raise ValueError("ready worker identity files changed")
        if (
            receipt.admitted_environment is None
            or pin(receipt.admitted_environment.path) != receipt.admitted_environment
        ):
            raise ValueError("effective launched driver environment missing or changed")
        driver_env = TypeAdapter(dict[str, str]).validate_json(
            receipt.admitted_environment.path.read_bytes()
        )
        required_env = {
            "SAIL_MODE": "local-cluster",
            "SAIL_EXPERIMENTAL_EXTENSIONS": "1",
            "SAIL_GRAPH_UTILS_ROOT": (plan.output / "staging").as_uri(),
            "SAIL_EXPERIMENTAL_PROCESS_WORKERS": "1",
            "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
            "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(
                plan.pool_bytes_per_process
            ),
            "SAIL_CLUSTER__WORKER_INITIAL_COUNT": "2",
            "SAIL_CLUSTER__WORKER_MAX_COUNT": "2",
            "SAIL_CLUSTER__WORKER_TASK_SLOTS": str(plan.worker_task_slots),
            "SAIL_EXECUTION__DEFAULT_PARALLELISM": str(plan.partitions),
            "SAIL_CLUSTER__TASK_MAX_ATTEMPTS": "1",
            "TOKIO_WORKER_THREADS": "16",
            "RAYON_NUM_THREADS": "16",
        }
        if any(driver_env.get(key) != value for key, value in required_env.items()):
            raise ValueError("driver admitted resource/runtime environment differs")
        logs: dict[int, str] = {}
        identity_by_id: dict[int, WorkerIdentity] = {}
        for identity in sorted(plan.output.glob("worker-*.json")):
            worker = WorkerIdentity.model_validate_json(identity.read_bytes())
            if worker.pgid != receipt.server_pid or worker.argv != [
                str(plan.binary.path),
                "worker",
            ]:
                raise ValueError(
                    "actual executed worker does not bind owned server/binary"
                )
            if any(
                worker.admitted_environment.get(key) != value
                for key, value in required_env.items()
            ):
                raise ValueError(
                    "actual worker inherited different resource/runtime environment"
                )
            identity_by_id[int(worker.worker_id)] = worker
            logs[int(worker.worker_id)] = identity.with_suffix(".log").read_text()
            report.workers.append(worker)
        if len(logs) != 2 or set(logs) != set(readiness.worker_ids):
            raise ValueError("two distinct ready worker identities required")
        report.configured_pools_bound_to_executed_processes = True
        original_pins = [
            pin(item) for item in sorted(plan.output.rglob("*")) if item.is_file()
        ]
        required_name = (
            "reference-bfs-full-parquet"
            if plan.kind == "reference"
            else "explicit-1mib-pool-refusal"
        )
        if len(receipt.actions) != 1 or receipt.actions[0].name != required_name:
            raise ValueError("exact planned data action missing")
        action = receipt.actions[0]
        if (
            action.seconds is None
            or action.finished_utc is None
            or action.server_log_end is None
            or action.server_log_start < readiness.server_log_end
            or action.worker_log_start.keys() != action.worker_log_end.keys()
            or len(action.worker_log_start) != 2
        ):
            raise ValueError("action completion/driver and worker byte windows missing")
        action_driver = driver[action.server_log_start : action.server_log_end].decode()
        jobs = {int(match.group(1)) for match in JOB.finditer(action_driver)}
        workers, attempts = task_evidence(logs, jobs)
        if not jobs or not attempts or len(workers) != 2:
            raise ValueError(
                "query jobs/tasks did not execute on both identified workers"
            )
        report.job_ids, report.worker_ids_executing, report.worker_task_attempts = (
            sorted(jobs),
            workers,
            attempts,
        )
        report.exchange_in_executed_plan = (
            "RepartitionExec" in action_driver or "ShuffleWriteExec" in action_driver
        )
        if not report.exchange_in_executed_plan:
            raise ValueError("actual keyed exchange unobserved")
        report.evidence_query_errors = receipt.evidence_query_errors
        if plan.kind == "reference":
            if action.error or action.expected_error or receipt.evidence_query_errors:
                raise ValueError("reference action or observer failed")
            verify_reference(receipt, report)
        else:
            if (
                not action.expected_error
                or not action.error
                or "unexpectedly succeeded" in action.error
            ):
                raise ValueError("explicit tiny-pool induced error not observed")
            report.observed_client_error = action.error
            for worker in identity_by_id.values():
                log_path = plan.output / f"worker-{worker.pid}.log"
                start, end = (
                    action.worker_log_start[str(log_path)],
                    action.worker_log_end[str(log_path)],
                )
                raw = log_path.read_bytes()[start:end].decode()
                report.memory_witnesses.extend(
                    memory_witnesses(raw, worker, pin(log_path), start, end, jobs)
                )
            if not report.memory_witnesses:
                raise ValueError(
                    "no attributable task-bound allocation cause before task report/cleanup; generic transport alone unqualified"
                )
        report.retained = original_pins
        if any(pin(record.path) != record for record in original_pins):
            raise ValueError("closed physical output/log bytes changed during oracle")
        report.outcome = "passed_scoped_native_probe"
    except Exception as error:  # noqa: BLE001 - preserve concrete unproved/mismatched scope
        report.errors.append(repr(error))
    finally:
        if pin(path) != before:
            report.outcome = "error"
            report.errors.append("closed child receipt changed during oracle")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            stream.write(report.model_dump_json(indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(
        0
        if verify(args.receipt, args.output).outcome == "passed_scoped_native_probe"
        else 1
    )


if __name__ == "__main__":
    main()
