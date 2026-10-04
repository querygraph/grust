"""Complete native owner/topology and actual partition task evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping

from pydantic import JsonValue

import control_io as io
import control_models as m
import owner_models as o


def number(record: m.NativeRecord, key: str) -> int:
    value = (record.__pydantic_extra__ or {}).get(key)
    io.require(
        type(value) is int and value >= 0, f"native nonnegative integer {key} absent"
    )
    if type(value) is not int:
        raise ValueError("native integer missing")
    return value


def detail(record: m.NativeRecord, key: str) -> JsonValue:
    values = record.__pydantic_extra__ or {}
    io.require(key in values, f"native detail {key} absent")
    return values[key]


def prove(
    records: list[m.NativeRecord],
    request: Mapping[str, object],
    stages: list[dict[str, JsonValue]],
    tasks: list[m.TaskStatus],
    *,
    cap: bool,
) -> m.NativeProof:
    io.require(
        request.get("algorithm") == "bfs_reference"
        and type(request.get("version")) is int
        and request["version"] == 3
        and request.get("partitions") == 32
        and request.get("vertices") == 13
        and request.get("source") == -5
        and request.get("max_levels") == (0 if cap else 8),
        "actual signed tiny native request differs",
    )
    io.require(
        bool(records) and len({(r.session_id, r.job_id) for r in records}) == 1,
        "one selected native session/job required",
    )
    session, job = records[0].session_id, records[0].job_id
    grouped: dict[int, list[m.NativeRecord]] = defaultdict(list)
    for record in records:
        grouped[record.partition].append(record)
    io.require(set(grouped) == set(range(32)), "complete native owner domain required")
    owners: dict[int, m.NativeRecord] = {}
    failures: list[m.NativeRecord] = []
    vertices = frontier = reached = 0
    for partition, events in grouped.items():
        io.require(
            len({(r.worker_id, r.pid, r.adjacency_id) for r in events}) == 1,
            "owner incarnation changed",
        )
        counts: Counter[str] = Counter(r.event for r in events)
        expected = {
            "init": 1,
            "decide": 1 if cap else 9,
            "apply": 1 if cap else 9,
            "close": 1,
        }
        io.require(
            all(counts[name] == value for name, value in expected.items()),
            "native event schedule incomplete or replayed",
        )
        init = next(r for r in events if r.event == "init")
        close = next(r for r in events if r.event == "close")
        apply0 = next((r for r in events if r.event == "apply" and r.phase == 0), None)
        io.require(apply0 is not None, "phase-zero topology application missing")
        if apply0 is None:
            raise ValueError("missing native topology application")
        owners[partition] = init
        io.require(
            init.phase == 0
            and detail(init, "mode") == "topology"
            and number(init, "levels") == 0,
            "invalid native initialization",
        )
        for event in ("decide", "apply"):
            selected = [r for r in events if r.event == event]
            io.require(
                {r.phase for r in selected} == set(range(1 if cap else 9)),
                "native phase set incomplete",
            )
            if event == "apply":
                io.require(
                    all(number(r, "output_phase") == r.phase + 1 for r in selected),
                    "native apply output phase differs",
                )
            first = next(r for r in selected if r.phase == 0)
            io.require(
                detail(first, "mode") == "topology" and number(first, "levels") == 0,
                "complete phase-zero topology required",
            )
        io.require(
            close.phase == (1 if cap else 9)
            and number(close, "levels") == (0 if cap else 8),
            "native owner close phase/levels differs",
        )
        io.require(
            close.location.byte_offset > apply0.location.byte_offset,
            "native close preceded topology",
        )
        vertices += number(apply0, "vertices")
        frontier += number(apply0, "frontier_vertices")
        reached += number(apply0, "local_reached")
        if cap:
            io.require(
                not counts["result"]
                and counts["failure"] <= 1
                and number(close, "local_reached") == number(apply0, "local_reached"),
                "cap must close without result or replayed cause",
            )
            for failure in (r for r in events if r.event == "failure"):
                io.require(
                    failure.phase == 1
                    and detail(failure, "code") == "bfs_level_cap"
                    and detail(failure, "outcome") == "nonconverged"
                    and number(failure, "levels") == number(failure, "max_levels") == 0
                    and number(failure, "frontier_vertices")
                    == number(failure, "reached")
                    == 1,
                    "native typed cap payload differs",
                )
                io.require(
                    apply0.location.byte_offset
                    < failure.location.byte_offset
                    < close.location.byte_offset,
                    "cap cause not between topology and owner close",
                )
                failures.append(failure)
        else:
            io.require(
                counts["result"] == 1 and counts["failure"] == 0,
                "positive native owner result missing or failed",
            )
            result = next(r for r in events if r.event == "result")
            io.require(
                result.phase == 9
                and detail(result, "converged") is True
                and number(result, "levels") == 8
                and number(result, "reached") == 11
                and number(result, "local_reached") == number(close, "local_reached"),
                "positive terminal native payload differs",
            )
    io.require(
        vertices == 13
        and frontier == reached == 1
        and {r.worker_id for r in owners.values()} == {1, 2},
        "topology cardinalities or both physical workers absent",
    )
    io.require(not cap or bool(failures), "native cap cause absent")
    native = [
        row
        for row in stages
        if row.get("session_id") == session
        and row.get("job_id") == job
        and str(row.get("slot_group", "")).startswith("worker-extension:")
    ]
    stage_ids: list[int] = []
    for row in native:
        value = row.get("stage")
        io.require(
            type(value) is int
            and row.get("partitions") == 32
            and row.get("placement") == "Worker"
            and row.get("mode") == "Pipelined",
            "native stage physical layout differs",
        )
        if type(value) is not int:
            raise ValueError("stage must be integer")
        stage_ids.append(value)
    io.require(
        len(native) == len(set(stage_ids)) == (4 if cap else 20)
        and len({str(row["slot_group"]) for row in native}) == 1,
        "native stage count/group differs",
    )
    selected_tasks = [
        t for t in tasks if t.key.job_id == job and t.key.stage in stage_ids
    ]
    io.require(
        bool(selected_tasks) and {t.worker_id for t in selected_tasks} == {1, 2},
        "both actual workers need native task evidence",
    )
    successes: set[tuple[int, int]] = set()
    for task in selected_tasks:
        io.require(
            task.worker_id == owners[task.key.partition].worker_id,
            "task actual owner physical worker differs",
        )
        if not cap:
            io.require(
                task.status in ("RUNNING", "SUCCEEDED"), "positive native task failure"
            )
            if task.status == "SUCCEEDED":
                key = task.key.stage, task.key.partition
                io.require(key not in successes, "duplicate successful native task")
                successes.add(key)
    if not cap:
        io.require(
            successes
            == {(stage, partition) for stage in stage_ids for partition in range(32)},
            "full stage/partition successes missing",
        )
    else:
        io.require(
            any(t.status == "FAILED" for t in selected_tasks),
            "cap has no actual failed native task",
        )
    return m.NativeProof(
        job_id=job,
        session_id=session,
        stages=stage_ids,
        owners=owners,
        successful_tasks=len(successes),
        cap_failures=failures,
    )


def worker_records(receipt: o.OwnerReceipt) -> dict[int, o.RemoteReceipt]:
    selected = [r for r in receipt.host_receipts if r.request.role == "worker"]
    io.require(
        len(selected) == 2 and {r.request.worker_id for r in selected} == {1, 2},
        "two actual worker records required",
    )
    return {
        int(r.request.worker_id): r for r in selected if r.request.worker_id is not None
    }
