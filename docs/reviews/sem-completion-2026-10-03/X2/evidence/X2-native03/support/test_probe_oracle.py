"""Offline controls reject transport-only, unbound and reversed cause evidence."""

from pathlib import Path

import probe_models as m
import probe_oracle as o


def worker() -> o.WorkerIdentity:
    return o.WorkerIdentity(
        pid=11,
        pgid=10,
        ppid=10,
        worker_id="2",
        session_id="s",
        dyld_library_path=None,
        argv=["/binary", "worker"],
        admitted_environment={},
    )


def evidence(raw: str) -> list[o.MemoryWitness]:
    record = m.Pin(path=Path("/raw.log"), bytes=len(raw), sha256="0" * 64)
    return o.memory_witnesses(raw, worker(), record, 0, len(raw), {1})


KEY = "key=TaskKey { job_id: JobId(1), stage: 0, partition: 0, attempt: 0 }"
CAUSE = f"execution_failure pid=11 event=task_execution_error {KEY} error_chain=Resources exhausted: Failed to allocate additional 131072 bytes"
REPORT = f"task_failure pid=11 session_id=s worker_id=Some(WorkerId(2)) {KEY} message=pool refusal cause=Resources exhausted"


def test_bound_allocation_before_task_report() -> None:
    witnesses = evidence(CAUSE + "\n" + REPORT)
    assert len(witnesses) == 1
    assert witnesses[0].task_key == (1, 0, 0, 0)
    assert witnesses[0].global_first_fault_proven is False


def test_generic_h2_does_not_qualify_allocation_cause() -> None:
    generic = CAUSE.replace(
        "Resources exhausted: Failed to allocate additional 131072 bytes",
        "h2 protocol error: error reading a body from connection",
    )
    assert not evidence(generic + "\n" + REPORT)


def test_wrong_pid_or_worker_or_job_does_not_qualify() -> None:
    assert not evidence(CAUSE.replace("pid=11", "pid=12") + "\n" + REPORT)
    assert not evidence(CAUSE + "\n" + REPORT.replace("WorkerId(2)", "WorkerId(3)"))
    assert not evidence((CAUSE + "\n" + REPORT).replace("JobId(1)", "JobId(2)"))


def test_reversed_report_cause_order_does_not_qualify() -> None:
    assert not evidence(REPORT + "\n" + CAUSE)


def test_offline_independent_fixture_reference() -> None:
    rows = o.reference_rows(Path(__file__).parents[1] / "fixture01")
    assert len(rows) == 4096
    assert sum(row.distance is not None for row in rows) == 4095
    assert next(row for row in rows if row.id == -(2**63)).distance is None
    assert next(row for row in rows if row.id == 2**63 - 1).distance is not None
