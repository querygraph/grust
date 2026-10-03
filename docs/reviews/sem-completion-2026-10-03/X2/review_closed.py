"""Offline second review of closed X2 artifacts; never connect to an engine."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, TypeAdapter

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
META = BASE / "X2-native04"
RAW = Path("/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x2-native04")
TASK = re.compile(r"job (\d+) stage (\d+) partition (\d+) attempt (\d+) execution plan")
JOB = re.compile(r"job (\d+) execution plan")


class Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)


class Pin(Record):
    path: Path
    bytes: int
    sha256: str


class Source(Record):
    head: str
    tree: str
    status: str


class Action(Record):
    server_log_start: int
    server_log_end: int
    worker_log_start: dict[str, int]
    worker_log_end: dict[str, int]
    error: str | None
    expected_error: bool


class Receipt(Record):
    outcome: Literal["completed_unqualified"]
    server_pid: int
    server_returncode: int
    server_wait_completed: Literal[True]
    shutdown_sigint: Literal[True]
    shutdown_sigkill: Literal[False]
    server_group_absent: Literal[True]
    worker_groups_absent: Literal[True]
    worker_pids: list[int]
    source_before: Source
    source_after: Source
    inputs_before: dict[str, Pin]
    inputs_after: dict[str, Pin]
    actions: list[Action]
    errors: list[str]
    graph_iterations: int | None
    graph_converged: bool | None
    historical_original_cause: Literal["unexplained"]


class Worker(Record):
    pid: int
    pgid: int
    worker_id: str
    session_id: str
    admitted_environment: dict[str, str]


class Witness(Record):
    worker_id: int
    pid: int
    log: Pin
    log_start: int
    log_end: int
    task_key: tuple[int, int, int, int]
    execution_failure_line: str
    task_failure_line: str
    execution_failure_precedes_task_failure: Literal[True]
    within_query_before_shutdown: Literal[True]
    global_first_fault_proven: Literal[False]


class Oracle(Record):
    outcome: Literal["passed_scoped_native_probe"]
    receipt: Pin
    workers: list[Worker]
    job_ids: list[int]
    worker_task_attempts: int
    worker_ids_executing: list[int]
    retained: list[Pin]
    memory_witnesses: list[Witness]
    errors: list[str]
    historical_original_cause: Literal["unexplained"]


class Wait(Record):
    status: Literal["actual_owner_wait_passed"]
    returncode: Literal[0]
    actual_wait_completed: Literal[True]
    owner_group_absent: Literal[True]
    forced_kill: Literal[False]
    source_unchanged: Literal[True]
    source_before: list[Pin]
    source_after: list[Pin]
    errors: list[str]


class Call(Record):
    returncode: Literal[0]
    wait_completed: Literal[True]
    child_group_absent: Literal[True]
    forced_cleanup: Literal[False]
    oracle_returncode: Literal[0]
    oracle_wait_completed: Literal[True]
    oracle_group_absent: Literal[True]


class Owner(Record):
    outcome: Literal["completed_scoped_native_probe_queue"]
    calls: list[Call]
    owned_locks_released: Literal[True]
    errors: list[str]


class Row(Record):
    id: int
    distance: float | None
    hops: int | None
    parent: int | None


def pin(path: Path) -> Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    data = path.read_bytes()
    return Pin(path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def check(record: Pin, seen: dict[Path, Pin]) -> None:
    actual = seen.setdefault(record.path, pin(record.path))
    if actual != record:
        raise ValueError(f"changed identity: {record.path}")


def main() -> None:
    seen: dict[Path, Pin] = {}
    wait = Wait.model_validate_json((META / "queue01/wait.json").read_bytes())
    owner = Owner.model_validate_json(
        (META / "queue01/owner/receipt.json").read_bytes()
    )
    if (
        wait.errors
        or owner.errors
        or wait.source_before != wait.source_after
        or len(owner.calls) != 2
    ):
        raise ValueError("owner/wait source or lifecycle differs")
    for record in wait.source_before:
        check(record, seen)
    cells: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    witness_worker_ids: set[int] = set()
    for name in ["x2-reference-p16-01", "x2-pool-refusal-p16-01"]:
        output = RAW / name
        receipt = Receipt.model_validate_json((output / "receipt.json").read_bytes())
        oracle = Oracle.model_validate_json(
            (META / f"queue01/owner/{name}-oracle.json").read_bytes()
        )
        if receipt.errors or oracle.errors or receipt.server_returncode not in (0, -2):
            raise ValueError("producer/oracle error")
        if (
            receipt.source_before != receipt.source_after
            or receipt.source_before.status
        ):
            raise ValueError("source closure differs")
        if receipt.inputs_before != receipt.inputs_after or len(receipt.actions) != 1:
            raise ValueError("input closure or action count differs")
        for record in [
            oracle.receipt,
            *oracle.retained,
            *receipt.inputs_before.values(),
        ]:
            check(record, seen)
        action = receipt.actions[0]
        driver = (output / "server.log").read_bytes()
        window = driver[action.server_log_start : action.server_log_end].decode()
        jobs = {int(match.group(1)) for match in JOB.finditer(window)}
        if sorted(jobs) != oracle.job_ids:
            raise ValueError("driver job byte window differs")
        tasks: dict[tuple[int, ...], int] = {}
        worker_logs: dict[int, bytes] = {}
        for worker in oracle.workers:
            if (
                worker.pgid != receipt.server_pid
                or worker.pid not in receipt.worker_pids
            ):
                raise ValueError("worker/server identity differs")
            log_path = output / f"worker-{worker.pid}.log"
            data = log_path.read_bytes()
            raw = data[
                action.worker_log_start[str(log_path)] : action.worker_log_end[
                    str(log_path)
                ]
            ].decode()
            for match in TASK.finditer(raw):
                key = tuple(int(value) for value in match.groups())
                if key[0] in jobs:
                    owner_id = int(worker.worker_id)
                    if key in tasks and tasks[key] != owner_id:
                        raise ValueError("task attempt seen on multiple workers")
                    tasks[key] = owner_id
            worker_logs[worker.pid] = data
        if len(tasks) != oracle.worker_task_attempts or sorted(set(tasks.values())) != [
            1,
            2,
        ]:
            raise ValueError("executed worker task evidence differs")
        if name.startswith("x2-reference"):
            vertices = pq.read_table(META / "fixture01/vertices.parquet")
            edges = pq.read_table(META / "fixture01/edges")
            if vertices.schema != pa.schema(
                [("id", pa.int64())]
            ) or edges.schema != pa.schema([("src", pa.int64()), ("dst", pa.int64())]):
                raise ValueError("fixture physical schema differs")
            ids: list[int] = vertices.column("id").to_pylist()
            if len(ids) != 4096 or len(set(ids)) != 4096 or edges.num_rows != 4097:
                raise ValueError("fixture cardinality differs")
            neighbors: dict[int, set[int]] = {vertex: set() for vertex in ids}
            for edge in edges.to_pylist():
                neighbors[edge["src"]].add(edge["dst"])
                neighbors[edge["dst"]].add(edge["src"])
            hops: dict[int, int] = {0: 0}
            queue = deque([0])
            while queue:
                src = queue.popleft()
                for dst in neighbors[src]:
                    if dst not in hops:
                        hops[dst] = hops[src] + 1
                        queue.append(dst)
            expected = [
                Row(
                    id=vertex,
                    distance=float(hops[vertex]) if vertex in hops else None,
                    hops=hops.get(vertex),
                    parent=(
                        0
                        if vertex == 0
                        else min(
                            n
                            for n in neighbors[vertex]
                            if hops.get(n) == hops[vertex] - 1
                        )
                    )
                    if vertex in hops
                    else None,
                )
                for vertex in sorted(ids)
            ]
            table = pq.read_table(sorted((output / "result").glob("*.parquet")))
            if {field.name: field.type for field in table.schema} != {
                "id": pa.int64(),
                "distance": pa.float64(),
                "hops": pa.int64(),
                "parent": pa.int64(),
            }:
                raise ValueError("output physical schema differs")
            actual = TypeAdapter(list[Row]).validate_python(table.to_pylist())
            if (
                sorted(actual, key=lambda row: row.id) != expected
                or len(hops) != 4095
                or max(hops.values()) != 11
            ):
                raise ValueError("independent full BFS differs")
            recorded = TypeAdapter(list[Row]).validate_json(
                (META / "fixture01/reference.json").read_bytes()
            )
            if (
                recorded != expected
                or not receipt.graph_converged
                or receipt.graph_iterations != 12
                or action.error
            ):
                raise ValueError("preserved oracle or convergence differs")
        else:
            if (
                not action.expected_error
                or action.error is None
                or "Failed to allocate" not in action.error
                or len(oracle.memory_witnesses) != 10
            ):
                raise ValueError("typed pool refusal not observed")
            for witness in oracle.memory_witnesses:
                witness_worker_ids.add(witness.worker_id)
                data = worker_logs[witness.pid]
                region = data[witness.log_start : witness.log_end]
                start = region.find(witness.execution_failure_line.encode())
                end = region.find(witness.task_failure_line.encode(), start + 1)
                if (
                    start < 0
                    or end <= start
                    or "Resources exhausted" not in witness.execution_failure_line
                    or "SingleHashAggregateStream" not in witness.execution_failure_line
                ):
                    raise ValueError("typed worker local failure order differs")
                event_rows.append(
                    {
                        "pid": witness.pid,
                        "worker_id": witness.worker_id,
                        "task_key": list(witness.task_key),
                        "log": str(witness.log.path),
                        "query_start_byte": witness.log_start,
                        "query_end_byte": witness.log_end,
                        "execution_failure_start_byte": witness.log_start + start,
                        "task_failure_start_byte": witness.log_start + end,
                        "execution_failure_line": witness.execution_failure_line,
                        "task_failure_line": witness.task_failure_line,
                        "local_order_qualified": True,
                        "global_first_fault_proven": False,
                    }
                )
        cells.append(
            {
                "run_id": name,
                "receipt": pin(output / "receipt.json").model_dump(mode="json"),
                "oracle": pin(META / f"queue01/owner/{name}-oracle.json").model_dump(
                    mode="json"
                ),
                "server_pid": receipt.server_pid,
                "worker_pids": receipt.worker_pids,
                "job_count": len(jobs),
                "task_attempts": len(tasks),
                "both_workers_executed": True,
                "actual_server_wait_closed": True,
                "typed_memory_witnesses": len(oracle.memory_witnesses),
            }
        )
    report = {
        "schema_version": 1,
        "observed_utc": datetime.now(UTC).isoformat(),
        "status": "independent_closed_x2_controls_review_passed",
        "cells": cells,
        "source": receipt.source_before.model_dump(),
        "full_reference_bfs": {
            "physical_rows": 4096,
            "reachable": 4095,
            "depth": 11,
            "rounds": 12,
            "original_id_domain_distances_hops_minimum_tight_parents_exact": True,
        },
        "induced_refusal": {
            "per_process_greedy_pool_bytes": 1048576,
            "input_distinct_groups": 1048576,
            "task_bound_local_witnesses": 10,
            "worker_ids_with_witnesses": sorted(witness_worker_ids),
            "global_first_fault_proven": False,
        },
        "owner": pin(META / "queue01/owner/receipt.json").model_dump(mode="json"),
        "actual_wait": pin(META / "queue01/wait.json").model_dump(mode="json"),
        "verified_pin_count": len(seen),
        "historical_original_cause": "unexplained",
        "historical_original_zero_event_cases": 12,
        "x1_two_host_qualification": False,
        "physical_memory_accounting_qualified": False,
        "native_os32_pss_accounting_qualified": False,
    }
    (META / "review/closed-controls.json").write_text(
        TypeAdapter(dict[str, object]).dump_json(report, indent=2).decode() + "\n"
    )
    (META / "review/allocation-local-order.json").write_text(
        TypeAdapter(list[dict[str, object]]).dump_json(event_rows, indent=2).decode()
        + "\n"
    )
    with (META / "review/full-reference-bfs.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "distance", "hops", "parent"])
        writer.writeheader()
        writer.writerows(row.model_dump() for row in expected)
    print("independent_closed_x2_controls_review_passed")


if __name__ == "__main__":
    main()
