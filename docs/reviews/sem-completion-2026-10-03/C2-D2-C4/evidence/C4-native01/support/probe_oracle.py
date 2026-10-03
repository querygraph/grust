"""Full bounded answer/log oracle, run only after the native child exits."""
import argparse
import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import probe_models as m
import worker_ready
from pydantic import Field

TASK = re.compile(r"job (\d+) stage (\d+) partition (\d+) attempt (\d+) execution plan")
JOB = re.compile(r"job (\d+) execution plan")


class ActionProof(m.Model):
    name: str
    full_answer_passed: bool
    rows: int
    job_ids: list[int]
    worker_ids: list[int]
    worker_task_attempts: int
    exchange_in_executed_plan: bool
    both_workers_observed: bool
    partition_count_observed: bool
    partial_and_final_aggregates_observed: bool
    ordered_last_value_in_plan: bool


class Oracle(m.Model):
    outcome: Literal["passed_scoped_native_probe", "error"] = "error"
    observed_utc: str
    receipt: m.Pin
    actions: list[ActionProof] = Field(default_factory=list)
    source_and_input_closure: bool = False
    child_server_closure: bool = False
    full_server_phase_attribution: Literal[False] = False
    physical_memory_accounting_qualified: Literal[False] = False
    allocation_state_size_qualified: Literal[False] = False
    compact_group_accumulator_observed: Literal[False] = False
    checkpoint_layout_preserved: bool = False
    checkpoint_layout_scope: str = "observed executed plans; no bucket filename inference"
    errors: list[str] = Field(default_factory=list)


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("oracle requires regular files")
    return m.Pin(path=path, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def verify_rows(rows: list[list[int]], expected: list[list[int]], schema: list[tuple[str, str]],
                names: list[str]) -> None:
    if schema != [(name, "bigint") for name in names]:
        raise ValueError("raw names/types differ")
    if any(len(row) != len(names) or any(type(x) is not int for x in row) for row in rows):
        raise ValueError("raw integer row shape differs")
    if sorted(rows) != expected:
        raise ValueError("full output differs (including missing/duplicate rows)")


def reference_rows(edges: list[list[int]]) -> list[list[int | float]]:
    groups: dict[int, list[tuple[float, int, int]]] = {}
    for src, dst, payload in edges:
        groups.setdefault(src, []).append((float(payload % 7), payload % 3, dst))
    if any(len(set(values)) != len(values) for values in groups.values()):
        raise ValueError("fixture requires unique full ordering tuples in each signed group")
    return [[src, *min(values)] for src, values in sorted(groups.items())]


def verify_c4_rows(rows: list[list[int | float]], expected: list[list[int | float]],
                   schema: list[tuple[str, str]]) -> None:
    fields = [("src", "bigint"), ("distance", "double"), ("hops", "bigint"), ("parent", "bigint")]
    if schema != fields:
        raise ValueError("raw C4 names/types differ")
    for row in rows:
        if len(row) != len(fields):
            raise ValueError("raw C4 field count differs")
        for value, (_, field_type) in zip(row, fields, strict=True):
            if (field_type == "bigint" and type(value) is not int) or (
                    field_type == "double" and (type(value) is not float or not math.isfinite(value))):
                raise ValueError("raw C4 scalar type/finite value differs")
    if sorted(rows) != expected:
        raise ValueError("full C4 output differs, including duplicates or missing signed groups")


def task_evidence(logs: dict[int, str], job_ids: set[int]) -> tuple[list[int], int]:
    workers = []
    tasks: set[tuple[int, ...]] = set()
    owners: dict[tuple[int, ...], int] = {}
    for worker_id, raw in logs.items():
        selected = {tuple(int(v) for v in match.groups()) for match in TASK.finditer(raw)
                    if int(match.group(1)) in job_ids}
        if selected:
            for task in selected:
                if task in owners and owners[task] != worker_id:
                    raise ValueError("same task attempt appears on different worker IDs")
                owners[task] = worker_id
            workers.append(worker_id)
            tasks.update((worker_id, *task) for task in selected)
    return sorted(workers), len(tasks)


def verify(path: Path, output: Path) -> Oracle:
    before = pin(path)
    receipt = m.Receipt.model_validate_json(path.read_bytes())
    plan = receipt.configuration
    report = Oracle(observed_utc=datetime.now(UTC).isoformat(), receipt=before)
    try:
        if receipt.outcome != "completed_unqualified" or receipt.errors or not receipt.finished_utc:
            raise ValueError("native child did not complete cleanly")
        if not receipt.server_wait_completed or not receipt.shutdown_sigint or receipt.server_returncode not in (0, -2) or receipt.shutdown_sigkill or not receipt.server_group_absent or not receipt.worker_groups_absent:
            raise ValueError("native child server/worker closure incomplete")
        if receipt.sampler_error:
            raise ValueError("RSS sampling failed")
        report.child_server_closure = True
        if receipt.inputs_before != receipt.inputs_after or receipt.source_before != receipt.source_after:
            raise ValueError("identity/source closure differs")
        for record in receipt.inputs_before.values():
            if pin(record.path) != record:
                raise ValueError("original/helper/client changed after child")
        report.source_and_input_closure = True
        required_names = ["cold-first-data-action", "warm-same-query-same-server"]
        if [action.name for action in receipt.actions] != required_names or any(
                action.seconds is None or action.seconds < 0 or action.finished_utc is None
                or action.server_log_end is None for action in receipt.actions):
            raise ValueError("exact planned action order/completion differs")
        reference = json.loads((plan.fixture / "reference.json").read_bytes())
        driver = (plan.output / "server.log").read_bytes()
        readiness = receipt.worker_readiness
        if readiness is None or len(readiness.worker_ids) != 2 or len(readiness.worker_pids) != 2:
            raise ValueError("two-worker startup readiness missing")
        if worker_ready.registered_ids(driver[:readiness.server_log_end].decode()) != set(readiness.worker_ids):
            raise ValueError("retained pre-action registration boundary differs")
        if any(action.server_log_start < readiness.server_log_end for action in receipt.actions):
            raise ValueError("measured action begins before startup readiness")
        if any(pin(record.path) != record for record in readiness.identity_files):
            raise ValueError("ready worker identity files changed")
        logs = {}
        for identity in plan.output.glob("worker-*.json"):
            record = json.loads(identity.read_bytes())
            if int(record["pgid"]) != receipt.server_pid or record["argv"] != [str(plan.binary.path), "worker"]:
                raise ValueError("worker identity does not bind owned server/binary")
            logs[int(record["worker_id"])] = identity.with_suffix(".log").read_text()
        if len(logs) != 2:
            raise ValueError("two distinct worker IDs required")
        for action in receipt.actions:
            if action.error and not action.expected_error:
                raise ValueError("unexpected data-action error")
            if not action.raw_schema:
                continue
            expected = reference_rows(reference["edges"])
            verify_c4_rows(action.raw_rows, expected, action.raw_schema)
            raw = driver[action.server_log_start:action.server_log_end].decode("utf-8")
            jobs = {int(match.group(1)) for match in JOB.finditer(raw)}
            workers, attempts = task_evidence(logs, jobs)
            exchange = "RepartitionExec" in raw or "ShuffleWriteExec" in raw
            partitions = bool(re.search(rf"(?:Hash|RoundRobinBatch)\([^\n]*\b{plan.partitions}\b", raw))
            partial_final = "AggregateExec: mode=Partial" in raw and "AggregateExec: mode=Final" in raw
            proof = ActionProof(name=action.name, full_answer_passed=True, rows=len(action.raw_rows),
                job_ids=sorted(jobs), worker_ids=workers, worker_task_attempts=attempts,
                exchange_in_executed_plan=exchange, both_workers_observed=len(workers) == 2,
                partition_count_observed=partitions, partial_and_final_aggregates_observed=partial_final,
                ordered_last_value_in_plan="last_value" in raw.lower())
            report.actions.append(proof)
            if not jobs or not attempts:
                raise ValueError(f"executed job/task attribution missing: {action.name}")
            if not exchange or not partitions or len(workers) != 2 or not partial_final:
                raise ValueError(f"required partial/final P-way exchange on both workers unproved: {action.name}")
        if len(report.actions) != 2:
            raise ValueError("exact aggregate cold/warm pair missing")
        # Executed aggregation and full answers do not measure allocator state.
        # Compact grouped accumulator use is source-inferred, never observed here.
        report.outcome = "passed_scoped_native_probe"
    except Exception as error:  # noqa: BLE001 - preserve concrete unproved/mismatched scope
        report.errors.append(repr(error))
    finally:
        if pin(path) != before:
            report.outcome = "error"
            report.errors.append("child receipt changed during oracle")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            stream.write(report.model_dump_json(indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.receipt, args.output).outcome == "passed_scoped_native_probe" else 1)


if __name__ == "__main__":
    main()
