"""Full original native schedule and physical task coverage, without graph data."""

from collections import Counter, defaultdict
from collections.abc import Mapping

from pydantic import JsonValue

import control_io as io
import control_logs as logs
import control_models as c
import full_models as m


def number(record: c.NativeRecord, key: str) -> int:
    value = (record.__pydantic_extra__ or {}).get(key)
    io.require(
        type(value) is int and value >= 0, f"native nonnegative integer {key} absent"
    )
    if type(value) is not int:
        raise ValueError("native number absent")
    return value


def detail(record: c.NativeRecord, key: str) -> JsonValue:
    values = record.__pydantic_extra__ or {}
    io.require(key in values, f"native {key} missing")
    return values[key]


def prove(
    records: list[c.NativeRecord],
    request: Mapping[str, object],
    stages: list[dict[str, JsonValue]],
    tasks: list[c.TaskStatus],
    reached: int,
    levels: int,
) -> m.Proof:
    expected = {
        "algorithm": "bfs_reference",
        "version": 3,
        "partitions": 32,
        "vertices": 16777216,
        "source": 13507776,
        "max_levels": 8,
    }
    io.require(
        all(
            type(request.get(k)) is type(v) and request.get(k) == v
            for k, v in expected.items()
        ),
        "actual fullscale protocol/source/geometry differs",
    )
    io.require(
        bool(records) and len({(r.session_id, r.job_id) for r in records}) == 1,
        "one fullscale native session/job required",
    )
    session, job = records[0].session_id, records[0].job_id
    grouped: dict[int, list[c.NativeRecord]] = defaultdict(list)
    for record in records:
        io.require(
            all(
                getattr(record, key) == request.get(key)
                for key in ("operation_id", "snapshot_id", "generation", "algorithm")
            ),
            "native request operation identity differs",
        )
        grouped[record.partition].append(record)
    io.require(set(grouped) == set(range(32)), "complete native owner domain required")
    owners: dict[int, c.NativeRecord] = {}
    vertices = arcs = initial_frontier = initial_reached = final_reached = 0
    for partition, events in grouped.items():
        io.require(
            len({(r.worker_id, r.pid, r.adjacency_id) for r in events}) == 1,
            "native owner incarnation changed",
        )
        io.require(
            Counter(r.event for r in events)
            == {"init": 1, "decide": 9, "apply": 9, "result": 1, "close": 1},
            "full native schedule incomplete, failed or duplicated",
        )
        init = next(r for r in events if r.event == "init")
        result = next(r for r in events if r.event == "result")
        close = next(r for r in events if r.event == "close")
        owners[partition] = init
        io.require(
            init.phase == 0
            and detail(init, "mode") == "topology"
            and number(init, "levels") == 0,
            "initial topology differs",
        )
        vertices += number(init, "vertices")
        arcs += number(init, "frontier_edges") + number(init, "remaining_edges")
        initial_frontier += number(init, "frontier_vertices")
        initial_reached += number(init, "local_reached")
        for kind in ("decide", "apply"):
            selected = [r for r in events if r.event == kind]
            io.require(
                {r.phase for r in selected} == set(range(9)),
                "native phase set incomplete",
            )
            if kind == "apply":
                io.require(
                    all(number(r, "output_phase") == r.phase + 1 for r in selected),
                    "native apply output phase differs",
                )
            phase0 = next(r for r in selected if r.phase == 0)
            io.require(
                detail(phase0, "mode") == "topology" and number(phase0, "levels") == 0,
                "phase0 is not topology",
            )
        io.require(
            result.phase == close.phase == 9
            and detail(result, "converged") is True
            and number(result, "levels") == number(close, "levels") == levels
            and number(result, "reached") == reached
            and number(result, "local_reached") == number(close, "local_reached"),
            "native result/close terminal counters differ from mathematics",
        )
        io.require(
            init.location.log == result.location.log == close.location.log
            and init.location.byte_offset
            < result.location.byte_offset
            < close.location.byte_offset,
            "owner event ordering differs",
        )
        final_reached += number(result, "local_reached")
    io.require(
        vertices == 16777216
        and arcs == 536870912
        and initial_frontier == initial_reached == 1
        and final_reached == reached
        and {r.worker_id for r in owners.values()} == {1, 2},
        "full initial/terminal geometry or both physical workers differs",
    )
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
            raise ValueError("native stage ID absent")
        stage_ids.append(value)
    io.require(
        len(stage_ids) == len(set(stage_ids)) == 20
        and len({str(row["slot_group"]) for row in native}) == 1,
        "native stage count/group differs",
    )
    successes: set[tuple[int, int]] = set()
    counts = {1: 0, 2: 0}
    for task in tasks:
        if task.key.job_id != job or task.key.stage not in stage_ids:
            continue
        io.require(
            task.worker_id == owners[task.key.partition].worker_id
            and task.status in ("RUNNING", "SUCCEEDED"),
            "native task channel/owner/failure differs",
        )
        if task.status == "SUCCEEDED":
            key = task.key.stage, task.key.partition
            io.require(key not in successes, "duplicate native success")
            successes.add(key)
            counts[task.worker_id] += 1
    io.require(
        successes == {(s, p) for s in stage_ids for p in range(32)}
        and all(counts.values()),
        "20x32 complete successful tasks on both physical workers required",
    )
    return m.Proof(
        job_id=job,
        session_id=session,
        stages=stage_ids,
        owners=owners,
        successful_tasks=len(successes),
        event_count=len(records),
        directed_init_arcs=arcs,
        initialized_vertices=vertices,
        terminal_reached=reached,
        terminal_levels=levels,
        worker_successes=counts,
    )


def native_tasks(
    raw: list[logs.Line],
    worker: int,
    records: list[c.NativeRecord],
    stages: list[dict[str, JsonValue]],
) -> list[c.TaskStatus]:
    """Exclude ordinary64-wide tasks BEFORE the native32 TaskKey constructor."""
    io.require(
        bool(records) and len({(r.job_id, r.session_id) for r in records}) == 1,
        "selected native job/session required for task adapter",
    )
    job, session = records[0].job_id, records[0].session_id
    stage_ids = {
        int(str(row["stage"]))
        for row in stages
        if type(row.get("stage")) is int
        and row.get("job_id") == job
        and row.get("session_id") == session
        and str(row.get("slot_group", "")).startswith("worker-extension:")
    }
    result: list[c.TaskStatus] = []
    for line in raw:
        if "worker_task_status " not in line.text:
            continue
        match = logs.STATUS.search(line.text)
        io.require(match is not None, "declared worker task status malformed")
        if match is None:
            raise ValueError("task status missing")
        channel, task_job, stage, partition, attempt = map(int, match.groups()[:5])
        io.require(
            channel == worker and worker in (1, 2),
            "status differs from retained physical worker channel",
        )
        if task_job != job or stage not in stage_ids:
            continue
        result.append(
            c.TaskStatus.model_validate(
                {
                    "key": {
                        "job_id": task_job,
                        "stage": stage,
                        "partition": partition,
                        "attempt": attempt,
                    },
                    "worker_id": worker,
                    "status": match[6],
                    "location": line.location,
                }
            )
        )
    return result
