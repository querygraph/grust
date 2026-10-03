"""Read complete closed host/native admission, refusal and release evidence."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Literal

import probe_models as m
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ConfigDict, Field, TypeAdapter


class Recorded(m.Model):
    model_config = ConfigDict(extra="ignore", strict=True)


class NativeMemory(Recorded):
    limit_bytes: int = Field(gt=0)
    used_bytes: int = Field(ge=0)
    peak_bytes: int = Field(ge=0)
    staged_bytes: int = Field(ge=0)


class Graph(Recorded):
    name: str
    node_count: int
    edge_count: int
    revision: int


class NativeStatus(Recorded):
    memory: NativeMemory
    graphs: list[Graph]


class Oracle(m.Model):
    outcome: Literal["passed_scoped_native_probe", "error"] = "error"
    observed_utc: str
    receipt: m.Pin
    actual_host_reservations: list[m.QuotaEvent] = Field(default_factory=list)
    native_status: dict[str, NativeStatus] = Field(default_factory=dict)
    observed_native_quota_refusal: str | None = None
    actual_closed_server_pid: int | None = None
    admitted_native_bytes: int = 0
    host_pool_bytes: int = 0
    declared_reservation_headroom_bytes: int = 0
    full_degree_output_passed: bool = False
    source_client_and_helper_closure: bool = False
    actual_owned_server_wait_and_group_absence: bool = False
    pool_transport_spill_oom_distinguished: bool = True
    full_nonpool_headroom_measured: Literal[False] = False
    transport_buffers_measured: Literal[False] = False
    operator_spill_measured: Literal[False] = False
    native_os32_pss_accounting_qualified: Literal[False] = False
    physical_memory_accounting_qualified: Literal[False] = False
    retained: list[m.Pin] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("oracle requires regular closed files")
    return m.Pin(
        path=path,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def verify_leases(
    events: list[m.QuotaEvent], pid: int, quota: int, identity: str
) -> None:
    """Require two real leases, ordered admission/release, exact host reservations."""
    if len(events) != 4 or [event.event for event in events] != [
        "admitted",
        "released",
        "admitted",
        "released",
    ]:
        raise ValueError(
            "exact first/replacement admission and final release sequence missing"
        )
    if any(
        event.pid != pid or event.bytes != quota or event.extension != identity
        for event in events
    ):
        raise ValueError(
            "audited native identity/quota does not bind actual server PID"
        )
    if (
        events[0].id == events[2].id
        or events[0].id != events[1].id
        or events[2].id != events[3].id
    ):
        raise ValueError("first and replacement lease identities differ or repeat")
    if [event.pool_reserved for event in events] != [quota, 0, quota, 0]:
        raise ValueError("actual host reservation/returned-zero evidence differs")
    if any(
        datetime.fromisoformat(left.timestamp_utc)
        > datetime.fromisoformat(right.timestamp_utc)
        for left, right in pairwise(events)
    ):
        raise ValueError("native accounting timestamps are not ordered")


def verify(path: Path, output: Path) -> Oracle:
    before = pin(path)
    receipt = m.Receipt.model_validate_json(path.read_bytes())
    plan = receipt.configuration
    report = Oracle(
        observed_utc=datetime.now(UTC).isoformat(),
        receipt=before,
        admitted_native_bytes=plan.native_quota_bytes,
        host_pool_bytes=plan.pool_bytes_per_process,
        declared_reservation_headroom_bytes=plan.pool_bytes_per_process
        - plan.native_quota_bytes,
    )
    try:
        if (
            receipt.outcome != "completed_unqualified"
            or receipt.errors
            or receipt.sampler_error
        ):
            raise ValueError("producer did not close successfully")
        if (
            not receipt.server_wait_completed
            or not receipt.server_group_absent
            or not receipt.worker_groups_absent
            or receipt.worker_pids
            or receipt.server_returncode not in (0, -2)
            or receipt.shutdown_sigkill
            or not receipt.shutdown_sigint
            or receipt.server_pid is None
        ):
            raise ValueError("owned local server actual wait/group closure missing")
        report.actual_owned_server_wait_and_group_absence = True
        report.actual_closed_server_pid = receipt.server_pid
        if (
            receipt.source_before != receipt.source_after
            or receipt.inputs_before != receipt.inputs_after
        ):
            raise ValueError("source/client/helper closure changed")
        if any(pin(record.path) != record for record in receipt.inputs_before.values()):
            raise ValueError("pinned source/client/helper bytes changed")
        report.source_client_and_helper_closure = True
        if (
            receipt.admitted_environment is None
            or pin(receipt.admitted_environment.path) != receipt.admitted_environment
        ):
            raise ValueError("launched environment absent/changed")
        env = TypeAdapter(dict[str, str]).validate_json(
            receipt.admitted_environment.path.read_bytes()
        )
        required = {
            "SAIL_MODE": "local",
            "SAIL_EXPERIMENTAL_EXTENSIONS": "1",
            "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
            "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(
                plan.pool_bytes_per_process
            ),
            "SAIL_NUTMEG_MEMORY_BYTES": str(plan.native_quota_bytes),
            "NUTMEG_MEMORY_BYTES": str(plan.native_quota_bytes),
            "NUTMEG_WORKERS": "16",
            "SAIL_NATIVE_RESOURCE_AUDIT": str(
                plan.output / "native-resource-audit.jsonl"
            ),
        }
        if any(env.get(key) != value for key, value in required.items()):
            raise ValueError("admitted actual resource/runtime settings differ")
        if (
            receipt.native_audit is None
            or pin(receipt.native_audit.path) != receipt.native_audit
        ):
            raise ValueError("actual completed quota audit missing or changed")
        original_pins = [
            pin(item) for item in sorted(plan.output.rglob("*")) if item.is_file()
        ]
        events = [
            m.QuotaEvent.model_validate_json(line)
            for line in receipt.native_audit.path.read_bytes().splitlines()
            if line
        ]
        verify_leases(
            events,
            receipt.server_pid,
            plan.native_quota_bytes,
            plan.native_package_identity,
        )
        report.actual_host_reservations = events
        if (
            set(receipt.session_ids) != {"first", "second", "replacement"}
            or len(set(receipt.session_ids.values())) != 3
        ):
            raise ValueError("three distinct actual session incarnations missing")
        required_names = [
            "first-native-stage-degree-full-parquet",
            "second-native-quota-admission-refusal",
            "first-session-stop",
            "replacement-admission-empty-state",
        ]
        if [action.name for action in receipt.actions] != required_names:
            raise ValueError("exact planned native resource action sequence missing")
        for action in receipt.actions:
            if (
                action.seconds is None
                or action.finished_utc is None
                or action.server_log_end is None
            ):
                raise ValueError("a native resource action is incomplete")
            if action.name != required_names[1] and (
                action.error or action.expected_error
            ):
                raise ValueError("unexpected native resource action error")
        refused = receipt.actions[1]
        if (
            not refused.expected_error
            or not refused.error
            or "host memory admission" not in refused.error
            or "refused" not in refused.error
            or str(plan.native_quota_bytes) not in refused.error
        ):
            raise ValueError(
                "native host admission refusal cause not observed; generic transport alone unqualified"
            )
        report.observed_native_quota_refusal = refused.error
        table = pq.read_table(sorted((plan.output / "result").glob("*.parquet")))
        if {field.name: field.type for field in table.schema} != {
            "id": pa.string(),
            "degree": pa.int64(),
        }:
            raise ValueError("canonical physical three-cycle output types differ")
        if sorted((row["id"], row["degree"]) for row in table.to_pylist()) != [
            ("0", 1),
            ("1", 1),
            ("2", 1),
        ]:
            raise ValueError("complete independent three-cycle degree oracle differs")
        report.full_degree_output_passed = True
        first = NativeStatus.model_validate_json(
            (plan.output / "first-native-status.json").read_bytes()
        )
        replacement = NativeStatus.model_validate_json(
            (plan.output / "replacement-native-status.json").read_bytes()
        )
        if (
            first.memory.limit_bytes != plan.native_quota_bytes
            or not 0 < first.memory.used_bytes <= plan.native_quota_bytes
        ):
            raise ValueError(
                "actual participating native budget/allocated bytes not observed"
            )
        if [
            (graph.name, graph.node_count, graph.edge_count, graph.revision)
            for graph in first.graphs
        ] != [("c3-cycle", 3, 3, 1)]:
            raise ValueError("native staged graph identity/count/revision differs")
        if (
            replacement.memory.limit_bytes != plan.native_quota_bytes
            or replacement.memory.used_bytes != 0
            or replacement.graphs
        ):
            raise ValueError(
                "replacement native session inherited graph state or budget differs"
            )
        report.native_status = {"first": first, "replacement": replacement}
        if any(pin(record.path) != record for record in original_pins):
            raise ValueError("closed output/audit/log bytes changed during oracle")
        report.retained = original_pins
        report.outcome = "passed_scoped_native_probe"
    except Exception as error:  # noqa: BLE001 - unproved resource scope never passes
        report.errors.append(repr(error))
    finally:
        if pin(path) != before:
            report.outcome = "error"
            report.errors.append("closed producer receipt changed during oracle")
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
