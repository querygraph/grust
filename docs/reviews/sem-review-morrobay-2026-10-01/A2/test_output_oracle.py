"""Small offline controls for both physical adapters; no engine/container work."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import numpy as np
import output_oracle as oracle
import pyarrow as pa
import pyarrow.parquet as pq


class OutputOracleControls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.wcc_path = self.root / "wcc-pairs.i64le"
        np.array([[1, 1], [2, 1], [5, 5], [9, 9]], dtype="<i8").tofile(self.wcc_path)
        self.wcc = oracle.load_wcc_reference(self.wcc_path, oracle.sha(self.wcc_path), 4, 9)
        self.ids_path = self.root / "ids.i64le"
        self.distances_path = self.root / "distances.i64le"
        np.array([1, 2, 5, 9], dtype="<i8").tofile(self.ids_path)
        np.array([0, 1, 2, -1], dtype="<i8").tofile(self.distances_path)
        self.bfs = oracle.load_bfs_reference(
            self.ids_path, oracle.sha(self.ids_path), self.distances_path,
            oracle.sha(self.distances_path), 4, 9, 1)

    def write_wcc(self, ids: Sequence[int | None], labels: Sequence[int | None], *,
                  name: str = "part.parquet", id_type: pa.DataType | None = None,
                  label_type: pa.DataType | None = None) -> None:
        target = self.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"id": pa.array(ids, type=id_type or pa.int64()),
                                 "component": pa.array(labels, type=label_type or pa.int64())}),
                       target)

    def write_bfs(self, engine: Literal["graphframes", "pecan"],
                  ids: Sequence[int | None], distances: Sequence[int | float | None], *,
                  name: str = "part.parquet", distance_type: pa.DataType | None = None) -> None:
        field = "dist_1" if engine == "graphframes" else "distance"
        physical_type = distance_type or (pa.int32() if engine == "graphframes" else pa.float64())
        target = self.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"id": pa.array(ids, type=pa.int64()),
                                 field: pa.array(distances, type=physical_type)}), target)

    def test_wcc_unordered_complete_partitioned(self) -> None:
        self.write_wcc([9, 2], [9, 1], name="a/first.parquet")
        self.write_wcc([5, 1], [5, 1], name="b/second.parquet")
        (self.output / "_SUCCESS").write_bytes(b"")
        result = oracle.verify_wcc_output(self.output, self.wcc)
        self.assertEqual((result.rows, result.unique, result.components), (4, 4, 3))
        self.assertEqual(result.largest_component_vertices, 2)
        self.assertEqual(len(result.result_files), 3)
        self.assertEqual(len(result.physical_schemas), 2)

    def test_wcc_false_merge(self) -> None:
        self.write_wcc([1, 2, 5, 9], [1, 1, 1, 9])
        with self.assertRaisesRegex(oracle.Mismatch, "membership mismatch"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_false_split(self) -> None:
        self.write_wcc([1, 2, 5, 9], [1, 2, 5, 9])
        with self.assertRaisesRegex(oracle.Mismatch, "membership mismatch"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_duplicate_within_file(self) -> None:
        self.write_wcc([1, 2, 5, 5, 9], [1, 1, 5, 5, 9])
        with self.assertRaisesRegex(oracle.Mismatch, "duplicate"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_duplicate_across_files(self) -> None:
        self.write_wcc([1, 2, 5, 9], [1, 1, 5, 9])
        self.write_wcc([1], [1], name="extra.parquet")
        with self.assertRaisesRegex(oracle.Mismatch, "duplicate"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_omission(self) -> None:
        self.write_wcc([1, 2, 5], [1, 1, 5])
        with self.assertRaisesRegex(oracle.Mismatch, "incomplete"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_unknown_sparse_id(self) -> None:
        self.write_wcc([1, 2, 3, 9], [1, 1, 3, 9])
        with self.assertRaisesRegex(oracle.Mismatch, "unknown"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_wcc_type_and_null_rejection(self) -> None:
        cases: list[tuple[pa.DataType, pa.DataType, list[int | None], list[int | None]]] = [
            (pa.int32(), pa.int64(), [1, 2, 5, 9], [1, 1, 5, 9]),
            (pa.int64(), pa.int32(), [1, 2, 5, 9], [1, 1, 5, 9]),
            (pa.int64(), pa.int64(), [1, None, 5, 9], [1, 1, 5, 9]),
            (pa.int64(), pa.int64(), [1, 2, 5, 9], [1, None, 5, 9]),
        ]
        for id_type, label_type, ids, labels in cases:
            with self.subTest(id_type=id_type, label_type=label_type, ids=ids, labels=labels):
                self.write_wcc(ids, labels, id_type=id_type, label_type=label_type)
                with self.assertRaises(oracle.Mismatch):
                    oracle.verify_wcc_output(self.output, self.wcc)

    def test_bfs_exact_physical_adapters(self) -> None:
        for engine in ("graphframes", "pecan"):
            with self.subTest(engine=engine):
                values: list[int | float | None] = [2, 2147483647, 0, 1] if engine == "graphframes" else [2.0, None, 0.0, 1.0]
                self.write_bfs(engine, [5, 9, 1, 2], values)
                result = oracle.verify_bfs_output(self.output, self.bfs, engine)
                self.assertEqual((result.rows, result.unique), (4, 4))
                self.assertEqual((result.reachable_vertices, result.unreachable_vertices), (3, 1))
                self.assertEqual(result.maximum_finite_distance, 2)
                self.assertEqual(result.physical_schemas[0].fields[1].arrow_type,
                                 "int32" if engine == "graphframes" else "double")

    def test_bfs_wrong_source_distance(self) -> None:
        self.write_bfs("graphframes", [1, 2, 5, 9], [1, 1, 2, 2147483647])
        with self.assertRaisesRegex(oracle.Mismatch, "distance mismatch"):
            oracle.verify_bfs_output(self.output, self.bfs, "graphframes")

    def test_bfs_wrong_finite_distance(self) -> None:
        self.write_bfs("pecan", [1, 2, 5, 9], [0.0, 1.0, 1.0, None])
        with self.assertRaisesRegex(oracle.Mismatch, "distance mismatch"):
            oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_bfs_unreachable_is_exact(self) -> None:
        for values in ([0.0, 1.0, None, None], [0.0, 1.0, 2.0, 3.0]):
            with self.subTest(values=values):
                self.write_bfs("pecan", [1, 2, 5, 9], values)
                with self.assertRaisesRegex(oracle.Mismatch, "distance mismatch"):
                    oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_bfs_invalid_pecan_finite_hops(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), -1.0, 0.5, 2147483647.0):
            with self.subTest(value=value):
                self.write_bfs("pecan", [1, 2, 5, 9], [0.0, value, 2.0, None])
                with self.assertRaisesRegex(oracle.Mismatch, "integral hop"):
                    oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_bfs_graphframes_null_and_negative(self) -> None:
        for value in (None, -1, -2):
            with self.subTest(value=value):
                self.write_bfs("graphframes", [1, 2, 5, 9], [0, 1, 2, value])
                with self.assertRaises(oracle.Mismatch):
                    oracle.verify_bfs_output(self.output, self.bfs, "graphframes")

    def test_bfs_schema_not_coerced(self) -> None:
        self.write_bfs("graphframes", [1, 2, 5, 9], [0, 1, 2, 2147483647], distance_type=pa.int64())
        with self.assertRaisesRegex(oracle.Mismatch, "schema"):
            oracle.verify_bfs_output(self.output, self.bfs, "graphframes")
        self.write_bfs("pecan", [1, 2, 5, 9], [0, 1, 2, None], distance_type=pa.int64())
        with self.assertRaisesRegex(oracle.Mismatch, "schema"):
            oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_bfs_actual_graphframes_column_order_is_read_by_name(self) -> None:
        # Observed A2 run03 physical layout: dist_1:Int32 precedes id:Int64.
        pq.write_table(pa.table({"dist_1": pa.array([2, 2147483647, 0, 1], type=pa.int32()),
                                 "id": pa.array([5, 9, 1, 2], type=pa.int64())}),
                       self.output / "part.parquet")
        result = oracle.verify_bfs_output(self.output, self.bfs, "graphframes")
        self.assertEqual((result.rows, result.unique, result.reachable_vertices), (4, 4, 3))
        self.assertEqual([field.name for field in result.physical_schemas[0].fields], ["dist_1", "id"])
        self.assertEqual([field.arrow_type for field in result.physical_schemas[0].fields], ["int32", "int64"])

    def test_bfs_named_fields_reject_extra_duplicate_and_wrong_type(self) -> None:
        cases = [
            pa.table({"dist_1": pa.array([0, 1, 2, 2147483647], type=pa.int32()),
                      "id": pa.array([1, 2, 5, 9], type=pa.int64()),
                      "extra": pa.array([1, 1, 1, 1], type=pa.int64())}),
            pa.Table.from_arrays([pa.array([1, 2, 5, 9], type=pa.int64()),
                                  pa.array([1, 2, 5, 9], type=pa.int64())], names=["id", "id"]),
            pa.table({"dist_1": pa.array([0, 1, 2, 2147483647], type=pa.int64()),
                      "id": pa.array([1, 2, 5, 9], type=pa.int64())}),
        ]
        for table in cases:
            with self.subTest(schema=table.schema):
                pq.write_table(table, self.output / "part.parquet")
                with self.assertRaisesRegex(oracle.Mismatch, "schema"):
                    oracle.verify_bfs_output(self.output, self.bfs, "graphframes")

    def test_bfs_duplicate_omit_unknown(self) -> None:
        cases: list[tuple[list[int | None], list[int]]] = [
                            ([1, 2, 2, 9], [0, 1, 1, 2147483647]),
                            ([1, 2, 5], [0, 1, 2]),
                            ([1, 2, 6, 9], [0, 1, 2, 2147483647]),
                            ([1, 2, 5, 10], [0, 1, 2, 2147483647]),
                            ([1, None, 5, 9], [0, 1, 2, 2147483647])]
        for ids, values in cases:
            with self.subTest(ids=ids):
                self.write_bfs("graphframes", ids, values)
                with self.assertRaises(oracle.Mismatch):
                    oracle.verify_bfs_output(self.output, self.bfs, "graphframes")

    def test_bfs_duplicate_across_files(self) -> None:
        self.write_bfs("pecan", [1, 2, 5, 9], [0.0, 1.0, 2.0, None])
        self.write_bfs("pecan", [5], [2.0], name="extra.parquet")
        with self.assertRaisesRegex(oracle.Mismatch, "duplicate"):
            oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_reference_hash_and_length_are_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            oracle.load_wcc_reference(self.wcc_path, "0" * 64, 4, 9)
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            oracle.load_wcc_reference(self.wcc_path, oracle.sha(self.wcc_path), 3, 9)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            oracle.load_bfs_reference(self.ids_path, oracle.sha(self.ids_path),
                                     self.distances_path, "0" * 64, 4, 9, 1)

    def test_reference_source_and_sentinels(self) -> None:
        with self.assertRaisesRegex(ValueError, "source is not a vertex"):
            oracle.load_bfs_reference(self.ids_path, oracle.sha(self.ids_path),
                                     self.distances_path, oracle.sha(self.distances_path), 4, 9, 3)
        np.array([1, 0, 2, -1], dtype="<i8").tofile(self.distances_path)
        with self.assertRaisesRegex(ValueError, "source distance"):
            oracle.load_bfs_reference(self.ids_path, oracle.sha(self.ids_path),
                                     self.distances_path, oracle.sha(self.distances_path), 4, 9, 1)
        np.array([0, 1, 2, 2147483647], dtype="<i8").tofile(self.distances_path)
        with self.assertRaisesRegex(ValueError, "invalid reference BFS distance"):
            oracle.load_bfs_reference(self.ids_path, oracle.sha(self.ids_path),
                                     self.distances_path, oracle.sha(self.distances_path), 4, 9, 1)

    def test_reference_order_and_canonicalization(self) -> None:
        np.array([[1, 1], [2, 2], [5, 9], [9, 9]], dtype="<i8").tofile(self.wcc_path)
        with self.assertRaisesRegex(ValueError, "representatives"):
            oracle.load_wcc_reference(self.wcc_path, oracle.sha(self.wcc_path), 4, 9)
        np.array([1, 5, 2, 9], dtype="<i8").tofile(self.ids_path)
        with self.assertRaisesRegex(ValueError, "order"):
            oracle.load_bfs_reference(self.ids_path, oracle.sha(self.ids_path),
                                     self.distances_path, oracle.sha(self.distances_path), 4, 9, 1)

    def test_no_parquet_and_symlink_rejected(self) -> None:
        with self.assertRaisesRegex(oracle.Mismatch, "no result Parquet"):
            oracle.verify_wcc_output(self.output, self.wcc)
        (self.output / "link").symlink_to(self.wcc_path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            oracle.verify_wcc_output(self.output, self.wcc)

    def test_complete_inventory_change_rejected(self) -> None:
        self.write_bfs("pecan", [1, 2, 5, 9], [0.0, 1.0, 2.0, None])
        (self.output / "_SUCCESS").write_bytes(b"")
        real_inventory = oracle.inventory
        calls = 0

        def mutate(directory: Path) -> dict[str, oracle.FileIdentity]:
            nonlocal calls
            calls += 1
            if calls == 2:
                (directory / "_SUCCESS").write_bytes(b"changed")
            return real_inventory(directory)

        with (patch("output_oracle.inventory", side_effect=mutate),
              self.assertRaisesRegex(ValueError, "changed during verification")):
            oracle.verify_bfs_output(self.output, self.bfs, "pecan")

    def test_truncated_parquet_is_not_a_mismatch_success(self) -> None:
        self.write_wcc([1, 2, 5, 9], [1, 1, 5, 9])
        target = self.output / "part.parquet"
        target.write_bytes(target.read_bytes()[:-12])
        with self.assertRaises(pa.ArrowInvalid):
            oracle.verify_wcc_output(self.output, self.wcc)


if __name__ == "__main__":
    unittest.main()
