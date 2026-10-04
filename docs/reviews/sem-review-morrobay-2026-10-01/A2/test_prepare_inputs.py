"""Independent tiny input-phase controls; no large data reads or engine runs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import numpy.typing as npt
import prepare_inputs as phase
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError


class PreparationControls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ids: npt.NDArray[np.int64] = np.array([1, 2, 5, 9, 12, 15], dtype=np.int64)
        self.sources: npt.NDArray[np.int64] = np.array([12, 1, 2, 9, 1, 5], dtype=np.int64)
        self.targets: npt.NDArray[np.int64] = np.array([12, 2, 5, 1, 2, 2], dtype=np.int64)
        self.csr = phase.build_csr(self.ids, self.sources, self.targets)
        self.correct: npt.NDArray[np.int64] = np.array([0, 1, 2, -1, -1, -1], dtype=np.int64)

    def test_directed_bfs_cycles_duplicates_isolates(self) -> None:
        actual = phase.breadth_first_distances(self.csr, 1)
        np.testing.assert_array_equal(actual, self.correct)
        self.assertEqual(len(self.csr.targets), 6)
        np.testing.assert_array_equal(self.csr.targets[:2], [1, 1])
        proof = phase.verify_bfs_certificate(self.csr, actual, 1)
        self.assertEqual((proof.reachable_vertices, proof.unreachable_vertices), (3, 3))
        self.assertEqual(proof.all_edges_examined, 6)
        self.assertEqual(proof.reachable_source_edges_examined, 4)
        self.assertEqual(proof.predecessor_witness_vertices, 2)

    def test_reverse_incoming_edge_does_not_reach_vertex(self) -> None:
        actual = phase.breadth_first_distances(self.csr, 1)
        self.assertEqual(int(actual[3]), -1)  # 9 -> 1 is not 1 -> 9.
        reverse_start = phase.breadth_first_distances(self.csr, 9)
        np.testing.assert_array_equal(reverse_start, [1, 2, 3, 0, -1, -1])
        phase.verify_bfs_certificate(self.csr, reverse_start, 9)

    def test_empty_edges_and_isolated_source(self) -> None:
        empty: npt.NDArray[np.int64] = np.array([], dtype=np.int64)
        csr = phase.build_csr(self.ids, empty, empty)
        actual = phase.breadth_first_distances(csr, 15)
        np.testing.assert_array_equal(actual, [-1, -1, -1, -1, -1, 0])
        proof = phase.verify_bfs_certificate(csr, actual, 15)
        self.assertEqual((proof.all_edges_examined, proof.predecessor_witness_vertices), (0, 0))

    def test_isolation_counts_incoming_edges_and_self_loops_as_incident(self) -> None:
        ids: npt.NDArray[np.int64] = np.array([1, 2, 5, 9], dtype=np.int64)
        sources: npt.NDArray[np.int64] = np.array([1, 5], dtype=np.int64)
        targets: npt.NDArray[np.int64] = np.array([2, 5], dtype=np.int64)
        csr = phase.build_csr(ids, sources, targets)
        # Vertex 2 has only an incoming edge; 5 has a self-loop; only 9 is isolated.
        self.assertEqual(phase.isolated_vertex_count(csr), 1)

    def test_missing_source_is_not_replaced(self) -> None:
        with self.assertRaisesRegex(ValueError, "source is not a vertex"):
            phase.breadth_first_distances(self.csr, 750000)

    def test_unsorted_vertices_become_canonical_order(self) -> None:
        np.testing.assert_array_equal(phase.sorted_vertices(self.ids[::-1]), self.ids)

    def test_duplicate_negative_and_wrong_vertex_type(self) -> None:
        for values in ([1, 1, 9], [-1, 2, 9], [0, 2, 9]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                phase.sorted_vertices(np.array(values, dtype=np.int64))
        with self.assertRaisesRegex(ValueError, "signed64"):
            phase.sorted_vertices(np.array([1, 2, 9], dtype=np.int32))

    def test_endpoint_membership_both_columns(self) -> None:
        for sources, targets in [([99], [1]), ([1], [99]), ([3], [1]), ([1], [3])]:
            with (self.subTest(sources=sources, targets=targets),
                  self.assertRaisesRegex(ValueError, "endpoint is not a vertex")):
                phase.build_csr(self.ids, np.array(sources, dtype=np.int64),
                                np.array(targets, dtype=np.int64))

    def test_parquet_schema_null_and_footer(self) -> None:
        path = self.root / "vertices.parquet"
        pq.write_table(pa.table({"id": pa.array([9, 1, 2], type=pa.int64())}), path)
        (actual,) = phase.read_columns(path, ["id"])
        np.testing.assert_array_equal(actual, [9, 1, 2])
        pq.write_table(pa.table({"id": pa.array([9, None, 2], type=pa.int64())}), path)
        with self.assertRaisesRegex(ValueError, "null"):
            phase.read_columns(path, ["id"])
        pq.write_table(pa.table({"id": pa.array([9, 1, 2], type=pa.int32())}), path)
        with self.assertRaisesRegex(ValueError, "schema"):
            phase.read_columns(path, ["id"])

    def test_inflated_and_reduced_hops_fail_certificate(self) -> None:
        for values in ([0, 2, 3, -1, -1, -1], [0, 1, 1, -1, -1, -1]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                phase.verify_bfs_certificate(self.csr, np.array(values, dtype=np.int64), 1)

    def test_unreachable_not_hidden_and_false_reach_rejected(self) -> None:
        for values in ([0, 1, -1, -1, -1, -1], [0, 1, 2, 3, -1, -1],
                       [0, 1, 2, -1, -1, 3]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                phase.verify_bfs_certificate(self.csr, np.array(values, dtype=np.int64), 1)

    def test_source_zero_is_unique_and_bound(self) -> None:
        for values in ([1, 2, 3, -1, -1, -1], [0, 0, 1, -1, -1, -1]):
            with (self.subTest(values=values),
                  self.assertRaisesRegex(ValueError, "only distance zero")):
                phase.verify_bfs_certificate(self.csr, np.array(values, dtype=np.int64), 1)

    def test_invalid_distance_domain_and_csr(self) -> None:
        with self.assertRaisesRegex(ValueError, "distance vector"):
            phase.verify_bfs_certificate(self.csr, np.array([0, 1, 2, -2, -1, -1], dtype=np.int64), 1)
        bad = phase.DirectedCsr(self.ids, np.array([0, 2, 3, 4, 5, 5, 5], dtype=np.int64),
                                self.csr.targets)
        with self.assertRaisesRegex(ValueError, "CSR topology"):
            phase.verify_bfs_certificate(bad, self.correct, 1)

    def test_portable_output_round_trip_and_exclusive_creation(self) -> None:
        path = self.root / "distances.i64le"
        artifact = phase.write_array(path, self.correct)
        self.assertEqual(artifact.identity.bytes, 6 * 8)
        self.assertEqual(path.read_bytes(), bytes.fromhex(
            "000000000000000001000000000000000200000000000000"
            "ffffffffffffffffffffffffffffffffffffffffffffffff"))
        np.testing.assert_array_equal(np.fromfile(path, dtype="<i8"), self.correct)
        with self.assertRaises(FileExistsError):
            phase.write_array(path, self.correct)

    def test_config_does_not_allow_borrowed_output_or_bad_source(self) -> None:
        with self.assertRaises(ValidationError):
            phase.InputConfig(inputs=self.root, output=self.root / "output", source=1)
        with self.assertRaises(ValidationError):
            phase.InputConfig(inputs=self.root, output=self.root.parent / "elsewhere", source=2**63)

    def test_failure_receipt_and_existing_directory_refusal(self) -> None:
        inputs = self.root / "inputs"
        inputs.mkdir()
        output = self.root / "new-output"
        config = phase.InputConfig(inputs=inputs, output=output, source=1)
        result = phase.prepare(config)
        self.assertEqual(result.outcome, "error")
        physical = phase.Receipt.model_validate_json((output / "receipt.json").read_bytes())
        self.assertEqual(physical.outcome, "error")
        self.assertIsNotNone(physical.finished_utc)
        self.assertIsNotNone(physical.memory)
        self.assertIn("missing/unsafe input", physical.error or "")
        with self.assertRaises(FileExistsError):
            phase.prepare(config)

    def test_changed_input_pin_retains_both_identities_without_writes(self) -> None:
        inputs = self.root / "inputs"
        inputs.mkdir()
        pq.write_table(pa.table({"id": pa.array([1], type=pa.int64())}),
                       inputs / "cit-Patents-v.parquet")
        pq.write_table(pa.table({"source": pa.array([1], type=pa.int64()),
                                 "target": pa.array([1], type=pa.int64())}),
                       inputs / "cit-Patents-e.parquet")
        np.array([[1, 1]], dtype="<i8").tofile(inputs / "wcc-membership.i64le")
        before = phase.original_identities(inputs)
        config = phase.InputConfig(inputs=inputs, output=self.root / "new-output", source=1)
        with self.assertLogs(phase.LOGGER, level="ERROR"):
            result = phase.prepare(config)
        self.assertEqual(result.outcome, "error")
        self.assertEqual(result.originals_before, before)
        self.assertEqual(result.originals_after, before)
        self.assertEqual(phase.original_identities(inputs), before)
        self.assertIn("vertex input hash mismatch", result.error or "")


if __name__ == "__main__":
    unittest.main()
