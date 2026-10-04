"""Offline compatibility fault controls; no child processes or engines launched."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import run_compatibility as compatibility


class CompatibilityControls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fixture(self) -> compatibility.TinyFixture:
        return compatibility.TinyFixture("signed-isolate", tuple(sorted((1, 2, compatibility.ISOLATE))),
            ((1, 2),), {1: 1, 2: 1, compatibility.ISOLATE: compatibility.ISOLATE}, 1)

    def control(self) -> compatibility.Control:
        return compatibility.Control(id="signed-witness", engine="pecan", algorithm="wcc-randomized",
                                     fixture="signed-isolate", source=1)

    def write_wcc(self, rows: Sequence[tuple[int, int | None]]) -> None:
        directory = self.root / "result"
        directory.mkdir(exist_ok=True)
        pq.write_table(pa.table({"id": pa.array([row[0] for row in rows], type=pa.int64()),
                                 "component": pa.array([row[1] for row in rows], type=pa.int64())}),
                       directory / "part.parquet")

    def test_exact_witness_records_known_mismatch(self) -> None:
        fixture, control = self.fixture(), self.control()
        self.write_wcc([(1, compatibility.ISOLATE), (2, compatibility.ISOLATE),
                        (compatibility.ISOLATE, compatibility.ISOLATE)])
        compatibility.check_output(control, fixture, self.root, self.root)
        self.assertEqual(control.outcome, "known_mismatch")
        self.assertEqual(len(control.raw_rows), 3)
        self.assertEqual(control.raw_rows[0].id, compatibility.ISOLATE)
        self.assertEqual(control.physical_schemas[0].fields[1].arrow_type, "int64")
        self.assertEqual(len(control.result_files), 1)

    def test_correct_witness_does_not_fabricate_known_mismatch(self) -> None:
        fixture, control = self.fixture(), self.control()
        self.write_wcc([(1, 1), (2, 1), (compatibility.ISOLATE, compatibility.ISOLATE)])
        compatibility.check_output(control, fixture, self.root, self.root)
        self.assertEqual(control.outcome, "passed")

    def test_other_mismatch_and_null_are_not_known_defect(self) -> None:
        for values in ([(1, 2), (2, 2), (compatibility.ISOLATE, compatibility.ISOLATE)],
                       [(1, None), (2, 1), (compatibility.ISOLATE, compatibility.ISOLATE)]):
            with self.subTest(values=values):
                fixture, control = self.fixture(), self.control()
                self.write_wcc(values)
                with self.assertRaisesRegex(ValueError, "unexpected signed-isolate mismatch"):
                    compatibility.check_output(control, fixture, self.root, self.root)
                self.assertEqual(len(control.raw_rows), 3)
                self.assertNotEqual(control.outcome, "known_mismatch")

    def test_duplicate_retains_raw_rows_but_rejects_coverage(self) -> None:
        self.write_wcc([(1, 1), (1, 1), (compatibility.ISOLATE, compatibility.ISOLATE)])
        control = self.control()
        with self.assertRaisesRegex(ValueError, "incomplete/duplicate"):
            compatibility.check_output(control, self.fixture(), self.root, self.root)
        self.assertEqual(len(control.raw_rows), 3)
        self.assertEqual(len(control.result_files), 1)

    def test_first_cleanup_observation_is_preserved(self) -> None:
        row = compatibility.Process(pid=123, name="owned-worker", state="S", starttime=42)
        control = self.control()
        control.closure_observed = True
        control.remaining_processes = [row]
        with patch("run_compatibility.processes", return_value=[]):
            compatibility.close_remaining(control)
        self.assertEqual(control.remaining_processes, [row])
        self.assertEqual(control.remaining_after_cleanup, [])

    def test_preexisting_process_is_refused_without_launch_or_kill(self) -> None:
        config = compatibility.Config(repo=self.root, harness_repo=self.root, support=self.root,
            output=self.root / "phase", binary=self.root / "sail", graphframes_binary=self.root / "gf",
            fixtures_root=self.root / "fixtures")
        row = compatibility.Process(pid=123, name="unknown-owner", state="S", starttime=42)
        control = self.control()
        with (patch("run_compatibility.processes", return_value=[row]),
              patch("run_compatibility.subprocess.Popen") as launch,
              patch("run_compatibility.os.kill") as kill,
              self.assertLogs(compatibility.LOGGER, level="ERROR")):
            compatibility.execute_control(config, control, self.fixture(), self.root)
        launch.assert_not_called()
        kill.assert_not_called()
        self.assertEqual(control.outcome, "error")
        self.assertEqual(control.remaining_after_cleanup, [row])

    def test_signed_parquet_generation_preserves_isolate(self) -> None:
        destination = compatibility.make_inputs(self.root, self.fixture())
        table = pq.read_table(destination / "vertices.parquet")
        self.assertEqual(table.schema.field("id").type, pa.int64())
        self.assertEqual(table.column("id").to_pylist(), [compatibility.ISOLATE, 1, 2])
        edges = pq.read_table(destination / "edges.parquet")
        self.assertEqual(edges.to_pylist(), [{"source": 1, "target": 2}])

    def test_bfs_actual_graphframes_order_preserved_in_raw_receipt(self) -> None:
        fixture = compatibility.TinyFixture("bfs-tiny", (1, 2, 9), ((1, 2),), {1: 0, 2: 1, 9: -1}, 1)
        inputs = compatibility.make_inputs(self.root, fixture)
        self.root.joinpath("result").mkdir()
        pq.write_table(pa.table({"dist_1": pa.array([2147483647, 1, 0], type=pa.int32()),
                                 "id": pa.array([9, 2, 1], type=pa.int64())}),
                       self.root / "result/part.parquet")
        control = compatibility.Control(id="bfs", engine="graphframes", algorithm="bfs", fixture=fixture.name, source=1)
        compatibility.check_output(control, fixture, inputs, self.root)
        self.assertEqual(control.outcome, "passed")
        self.assertEqual([(row.id, row.value) for row in control.raw_rows], [(1, 0), (2, 1), (9, 2147483647)])
        self.assertEqual([field.name for field in control.physical_schemas[0].fields], ["dist_1", "id"])


if __name__ == "__main__":
    unittest.main()
