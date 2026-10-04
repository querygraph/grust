"""Typed task/status/native log adapters with local byte-order witnesses."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import control_io as io
import control_models as m
import owner_models as o

TASK = re.compile(
    r"key=TaskKey \{ job_id: JobId\((\d+)\), stage: (\d+), partition: (\d+), attempt: (\d+) \}"
)
STATUS = re.compile(
    r"worker_task_status worker_id=(\d+) job_id=(\d+) stage=(\d+) partition=(\d+) attempt=(\d+) status=([A-Z_]+)\b"
)
QUOTED = r'"(?:[^"\\]|\\.)*"'
ALLOCATION = re.compile(
    r"failed to (?:allocate|grow)(?: additional)?|cannot allocate|allocation (?:failed|refused)|reservation[^\n]*(?:exceed|insufficient|refus)|memory (?:limit|budget)[^\n]*(?:exceed|exhaust)",
    re.IGNORECASE,
)
TRANSPORT = re.compile(
    r"h2 protocol|stream reset|connection reset|broken pipe|transport error|grpc_code=|host memory admission|native extension",
    re.IGNORECASE,
)
FFI_CAP_TEXT = "Execution error: argentea: BFS did not converge within max_levels"


@dataclass(frozen=True, slots=True)
class Line:
    location: m.Location
    text: str


def lines(expected: o.Pin) -> Iterator[Line]:
    io.require(io.pin(expected.path) == expected, "closed log identity differs")
    offset = 0
    with expected.path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            io.require(len(raw) <= 8 << 20, "unbounded log line")
            yield Line(
                m.Location(log=expected, line=number, byte_offset=offset),
                raw.decode("utf-8", errors="strict").rstrip("\n"),
            )
            offset += len(raw)


def task_key(text: str) -> m.TaskKey:
    match = TASK.search(text)
    io.require(match is not None, "typed task key absent")
    if match is None:
        raise ValueError("task key missing")
    job, stage, partition, attempt = map(int, match.groups())
    return m.TaskKey(job_id=job, stage=stage, partition=partition, attempt=attempt)  # type: ignore[arg-type]


def statuses(raw: list[Line]) -> list[m.TaskStatus]:
    result = []
    for line in raw:
        if "worker_task_status " not in line.text:
            continue
        match = STATUS.search(line.text)
        io.require(match is not None, "declared task status malformed")
        if match is None:
            raise ValueError("task status missing")
        worker, job, stage, partition, attempt = map(int, match.groups()[:5])
        result.append(
            m.TaskStatus.model_validate(
                {
                    "key": {
                        "job_id": job,
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


def worker_statuses(raw: list[Line], worker: int) -> list[m.TaskStatus]:
    result = statuses(raw)
    io.require(
        worker in (1, 2) and all(row.worker_id == worker for row in result),
        "task status differs from its actual owned worker log channel",
    )
    return result


def failed_reports(raw: list[Line]) -> list[m.FailedReport]:
    result = []
    for line in raw:
        if "ReportTaskStatusRequest {" not in line.text or not re.search(
            r"\bstatus: (?:Failed|2)(?=,|\s*})", line.text
        ):
            continue
        values = {
            key: int(value)
            for key, value in re.findall(
                r"\b(driver_id|job_id|stage|partition|attempt|sequence): (\d+)",
                line.text,
            )
        }
        io.require(
            set(values)
            == {"driver_id", "job_id", "stage", "partition", "attempt", "sequence"},
            "failed report task/driver/sequence incomplete",
        )
        decoded: dict[str, object] = {}
        for field in ("message", "cause"):
            match = re.search(r"\b" + field + r": Some\((" + QUOTED + r")\)", line.text)
            decoded[field] = json.loads(match[1]) if match else None
        io.require(
            isinstance(decoded["cause"], str), "typed failed report cause absent"
        )
        result.append(
            m.FailedReport.model_validate(
                {
                    "key": {
                        key: values[key]
                        for key in ("job_id", "stage", "partition", "attempt")
                    },
                    "driver_id": values["driver_id"],
                    "sequence": values["sequence"],
                    "message": decoded["message"],
                    "cause": json.loads(str(decoded["cause"])),
                    "location": line.location,
                }
            )
        )
    return result


def native_records(
    raw: list[Line], request: dict[str, object], worker: int, pid: int
) -> list[m.NativeRecord]:
    result = []
    for line in raw:
        if "ARGENTEA_RECEIPT " not in line.text:
            continue
        decoded = json.loads(line.text.split("ARGENTEA_RECEIPT ", 1)[1])
        io.require(isinstance(decoded, dict), "native receipt object required")
        if decoded.get("operation_id") != request.get("operation_id"):
            continue
        record = m.NativeRecord.model_validate({**decoded, "location": line.location})
        io.require(
            record.worker_id == worker
            and record.pid == pid
            and all(
                getattr(record, key) == request.get(key)
                for key in ("algorithm", "snapshot_id", "generation")
            ),
            "native operation/worker/PID/snapshot differs",
        )
        result.append(record)
    return result


def cause_text(cause: Mapping[str, object], *, cap: bool) -> str:
    io.require(len(cause) == 1, "exact externally tagged CommonErrorCause required")
    if isinstance(cause.get("execution"), str):
        return str(cause["execution"])
    if cap and isinstance(cause.get("python"), dict):
        value = cause["python"]
        if isinstance(value, dict) and isinstance(value.get("summary"), str):
            return str(value["summary"])
    raise ValueError("cause is not the declared typed execution/native Python error")


def classify(cause: Mapping[str, object], *, cap: bool) -> str:
    text = cause_text(cause, cap=cap)
    io.require(
        not TRANSPORT.search(text),
        "transport/startup/extension admission cause does not qualify",
    )
    if cap:
        io.require(
            "BFS did not converge within max_levels" in text,
            "typed task cause is not native BFS cap failure",
        )
        return "bfs_level_cap"
    io.require(
        bool(ALLOCATION.search(text)),
        "typed task execution payload lacks concrete allocation/reservation refusal",
    )
    return "allocation_refused"


def driver_teardown_order(report: m.Location, raw: list[Line], session: str) -> None:
    ended = [
        line
        for line in raw
        if re.search(
            r"\bremoving (?:idle )?session " + re.escape(session) + r"(?:\s|$)",
            line.text,
        )
    ]
    io.require(bool(ended), "actual driver session teardown evidence missing")
    io.require(
        all(
            report.log == line.location.log
            and report.byte_offset < line.location.byte_offset
            for line in ended
        ),
        "typed driver failure report must precede teardown in the same driver log",
    )


def native_bound_ffi_cap_text(
    report: m.FailedReport,
    status: m.TaskStatus,
    *,
    request: Mapping[str, object] | None,
    proof: m.NativeProof | None,
    native: m.NativeRecord | None,
    worker: int,
    pid: int,
    session: str,
) -> str:
    """Decode the stock4b FFI cap boundary only with a proven native cause.

    DataFusionError::Ffi becomes CommonErrorCause::Unknown in stock4b.
    This preserves that wire tag; it does not reclassify generic unknown errors.
    The caller still proves native -> execution -> task_failure -> FAILED order
    in the worker log and driver FAILED -> session removal in the driver log.
    """
    io.require(
        report.cause == {"unknown": FFI_CAP_TEXT}
        and report.message == f"task error: FFI error: {FFI_CAP_TEXT}",
        "exact stock4b FFI cap cause and message required",
    )
    io.require(
        native is not None and proof is not None and request is not None,
        "FFI cap requires complete native proof and actual request",
    )
    if native is None or proof is None or request is None:
        raise ValueError("native-bound FFI cap evidence absent")
    io.require(
        all(
            type(request.get(key)) is int and request.get(key) == value
            for key, value in {
                "version": 3,
                "max_levels": 0,
                "partitions": 32,
                "vertices": 13,
                "source": -5,
                "generation": native.generation,
            }.items()
        )
        and all(
            getattr(native, key) == request.get(key)
            for key in ("algorithm", "operation_id", "snapshot_id")
        ),
        "FFI cap request/operation/snapshot/generation mismatch",
    )
    owner = proof.owners.get(report.key.partition)
    detail = native.__pydantic_extra__ or {}
    io.require(
        native in proof.cap_failures
        and owner is not None
        and native.event == "failure"
        and native.phase == 1
        and detail.get("code") == "bfs_level_cap"
        and detail.get("outcome") == "nonconverged"
        and all(
            type(detail.get(key)) is int and detail.get(key) == value
            for key, value in {
                "levels": 0,
                "max_levels": 0,
                "frontier_vertices": 1,
                "reached": 1,
            }.items()
        )
        and native.job_id == proof.job_id == report.key.job_id
        and native.session_id == proof.session_id == session
        and report.key.stage in proof.stages
        and report.key == status.key
        and status.status == "FAILED"
        and native.partition == report.key.partition
        and native.worker_id == status.worker_id == worker
        and native.pid == pid
        and native.location.log == status.location.log,
        "FFI cap native payload/task/worker/PID/session/stage mismatch",
    )
    if owner is None:
        raise ValueError("native cap owner absent")
    io.require(
        all(
            getattr(owner, key) == getattr(native, key)
            for key in (
                "algorithm",
                "operation_id",
                "snapshot_id",
                "generation",
                "partition",
                "worker_id",
                "pid",
                "adjacency_id",
                "job_id",
                "session_id",
            )
        ),
        "FFI cap differs from the proven native owner incarnation",
    )
    return FFI_CAP_TEXT


def failure_witness(
    report: m.FailedReport,
    status: m.TaskStatus,
    raw: list[Line],
    *,
    worker: int,
    pid: int,
    session: str,
    native: m.NativeRecord | None = None,
    request: Mapping[str, object] | None = None,
    native_proof: m.NativeProof | None = None,
) -> m.CauseWitness:
    cap = native is not None
    ffi_cap = "unknown" in report.cause
    if ffi_cap:
        text = native_bound_ffi_cap_text(
            report,
            status,
            request=request,
            proof=native_proof,
            native=native,
            worker=worker,
            pid=pid,
            session=session,
        )
        classified = "bfs_level_cap"
    else:
        classified = classify(report.cause, cap=cap)
        text = cause_text(report.cause, cap=cap)
    io.require(
        report.key == status.key
        and status.worker_id == worker
        and status.status == "FAILED"
        and report.location.log != status.location.log,
        "typed driver report must bind matching FAILED status in a distinct worker log",
    )
    execution: Line | None = None
    failure: Line | None = None
    for line in raw:
        if (
            "execution_failure " in line.text
            and "event=task_execution_error " in line.text
            and f"pid={pid} " in line.text
            and task_key(line.text) == report.key
        ):
            chain = line.text.split("error_chain=", 1)[-1]
            matches = (
                chain == f"FFI error: {FFI_CAP_TEXT}"
                if ffi_cap
                else "BFS did not converge within max_levels" in chain
                if cap
                else bool(ALLOCATION.search(chain))
            )
            if matches and not TRANSPORT.search(chain):
                execution = line
        if (
            execution is not None
            and "task_failure " in line.text
            and f"pid={pid} " in line.text
            and f"worker_id=Some(WorkerId({worker}))" in line.text
            and f"session_id={session} " in line.text
            and task_key(line.text) == report.key
            and "cause=" in line.text
            and text in line.text.split("cause=", 1)[1]
            and (not ffi_cap or line.text.split("cause=", 1)[1] == FFI_CAP_TEXT)
        ):
            failure = line
            break
    io.require(
        execution is not None and failure is not None,
        "matching worker execution_failure and typed task_failure absent",
    )
    if execution is None or failure is None:
        raise ValueError("missing causal worker witness")
    io.require(
        execution.location.log == failure.location.log == status.location.log
        and execution.location.byte_offset
        < failure.location.byte_offset
        < status.location.byte_offset,
        "same worker log requires execution failure then task failure then FAILED status",
    )
    if native is not None:
        io.require(
            native.job_id == report.key.job_id
            and native.partition == report.key.partition
            and native.worker_id == worker
            and native.pid == pid
            and native.session_id == session
            and native.location.log == execution.location.log
            and native.location.byte_offset < execution.location.byte_offset,
            "native cap cause must precede same owner execution failure",
        )
    for line in raw:
        if re.search(
            r"\bremoving (?:idle )?session " + re.escape(session) + r"(?:\s|$)",
            line.text,
        ):
            io.require(
                failure.location.byte_offset < line.location.byte_offset,
                "task cause followed worker session teardown",
            )
    return m.CauseWitness.model_validate(
        {
            "key": report.key,
            "worker_id": worker,
            "pid": pid,
            "session_id": session,
            "classified_cause": classified,
            "typed_cause": report.cause,
            "rpc_tag": next(iter(report.cause)),
            "error_boundary": "datafusion_ffi_native_cap"
            if ffi_cap
            else "common_error_cause",
            "rpc_common_execution_tag_preserved": "execution" in report.cause,
            "native": native.location if native else None,
            "execution": execution.location,
            "task_failure": failure.location,
            "driver_report": report.location,
            "driver_failed_status": report.location,
            "worker_failed_status": status.location,
        }
    )
