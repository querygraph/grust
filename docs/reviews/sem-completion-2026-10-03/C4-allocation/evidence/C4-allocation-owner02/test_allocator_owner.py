"""Pure models, synthetic counters and mocked lifecycle; no Cargo/process launch."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import allocator_models as m
import allocator_owner as owner
import gate_owner as owned
from pydantic import ValidationError

ORIGINAL_PLAN = Path(__file__).with_name("original-run01-plan.json")


class AllocatorOwnerTests(unittest.TestCase):
    def plan(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(ORIGINAL_PLAN.read_bytes()))

    def test_default_and_bounded_probe_budget(self) -> None:
        plan = self.plan()
        del plan["probe_seconds"]
        self.assertEqual(m.Plan.model_validate(plan).probe_seconds, 600)
        for seconds in (10, 600, 900, 1800):
            plan["probe_seconds"] = seconds
            self.assertEqual(m.Plan.model_validate(plan).probe_seconds, seconds)
        for seconds in (9, 1801):
            plan["probe_seconds"] = seconds
            with self.assertRaises(ValidationError):
                m.Plan.model_validate(plan)

    def test_disjoint_namespace_and_disk_floors_remain_required(self) -> None:
        plan = self.plan()
        plan["cargo_home"] = plan["target"]
        with self.assertRaises(ValidationError):
            m.Plan.model_validate(plan)
        plan = self.plan()
        plan["minimum_free_bytes"] = 39 * 2**30
        with self.assertRaises(ValidationError):
            m.Plan.model_validate(plan)

    def test_timeout_identifies_probe_budget(self) -> None:
        with (
            patch.object(time, "monotonic", return_value=100.0),
            self.assertRaisesRegex(
                ValueError, r"step timeout expired: probe-04 .*900s"
            ),
        ):
            owner.check_step_deadline(1000.0, 100.0, "probe-04", 900)

    def test_campaign_timeout_remains_independent(self) -> None:
        with (
            patch.object(time, "monotonic", return_value=100.0),
            self.assertRaisesRegex(ValueError, "gate total timeout expired"),
        ):
            owner.check_step_deadline(100.0, 1000.0, "probe-04", 900)

    def record(self) -> m.Step:
        return m.Step(
            name="synthetic",
            argv=["not-executed"],
            pid=999999,
            pgid=999999,
            started_utc="synthetic-unit-control",
        )

    def test_forced_cleanup_records_actual_wait_and_absence(self) -> None:
        record = self.record()
        mocked_process = Mock(spec=subprocess.Popen)
        mocked_process.wait.return_value = -15
        process = cast(subprocess.Popen[bytes], mocked_process)
        with (
            patch.object(owned, "cleanup") as cleanup,
            patch.object(owned, "members", return_value=[]),
        ):
            owner.cleanup_step(process, record)
        cleanup.assert_called_once_with(record.pgid, process)
        mocked_process.wait.assert_called_once_with(timeout=5)
        self.assertEqual(record.returncode, -15)
        self.assertTrue(record.waited)
        self.assertTrue(record.group_absent)
        self.assertTrue(record.forced_cleanup)
        self.assertEqual(record.cleanup_errors, [])
        self.assertFalse(
            record.waited and record.group_absent and not record.forced_cleanup
        )

    def test_failed_cleanup_cannot_claim_wait_or_absence(self) -> None:
        record = self.record()
        mocked_process = Mock(spec=subprocess.Popen)
        mocked_process.wait.side_effect = subprocess.TimeoutExpired("not-executed", 5)
        process = cast(subprocess.Popen[bytes], mocked_process)
        with (
            patch.object(
                owned,
                "cleanup",
                side_effect=ValueError("synthetic cleanup failure"),
            ),
            patch.object(owned, "members", return_value=[record.pid]),
        ):
            owner.cleanup_step(process, record)
        self.assertIsNone(record.returncode)
        self.assertFalse(record.waited)
        self.assertFalse(record.group_absent)
        self.assertTrue(record.forced_cleanup)
        self.assertEqual(len(record.cleanup_errors), 3)

    def rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = [
            {"groups": 100000, "method": "PlannerOrderedMinBy"}
        ]
        for phase in owner.PHASES:
            rows.append(
                {
                    "phase": phase,
                    "seconds_exploratory_shared_host": 0.25,
                    "live_requested_before": 164733758,
                    "live_requested_after": 11335147,
                    "live_requested_change": -153398611,
                    "peak_requested_above_before": 1049500,
                    "allocations": 61,
                    "deallocations": 1700054,
                    "allocated_requested_bytes": 13797196,
                    "accumulator_reported_size": 240122269952,
                    "output_array_reported_bytes": 2400392,
                    "process_lifetime_peak_rss_bytes": 251457536,
                }
            )
        rows.append(
            {"checks": "passed", "groups": 100000, "method": "PlannerOrderedMinBy"}
        )
        return rows

    def qualify(self, rows: list[dict[str, Any]]) -> None:
        with tempfile.TemporaryDirectory(prefix="c4-source-control-") as directory:
            log = Path(directory) / "synthetic.log"
            log.write_text("".join(json.dumps(row) + "\n" for row in rows))
            owner.qualify_probe(log, 100000, "min-by")

    def test_reported_size_is_distinct_from_live_requested_and_rss(self) -> None:
        self.qualify(self.rows())

    def test_contradictory_counter_is_rejected(self) -> None:
        rows = self.rows()
        rows[1]["live_requested_change"] += 1
        with self.assertRaisesRegex(ValueError, "allocator change contradicts"):
            self.qualify(rows)

    def test_truncated_semantic_control_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "probe header/count"):
            self.qualify(self.rows()[:-1])

    def test_negative_request_count_is_rejected(self) -> None:
        rows = self.rows()
        rows[1]["allocations"] = -1
        with self.assertRaisesRegex(ValueError, "invalid requested allocator"):
            self.qualify(rows)

    def test_nonfinite_duration_is_rejected(self) -> None:
        rows = self.rows()
        rows[1]["seconds_exploratory_shared_host"] = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid phase duration"):
            self.qualify(rows)


if __name__ == "__main__":
    unittest.main()
