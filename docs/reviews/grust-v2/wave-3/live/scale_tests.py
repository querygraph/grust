"""Independent exact metadata and disjointness checks for the synthetic preparer."""

from __future__ import annotations

import unittest

from snb_dataset import Dataset, Table
from snb_scale import replicate


class ScaleTests(unittest.TestCase):
    def test_ids_endpoints_properties_and_exact_metadata(self) -> None:
        vertices = Table(
            1,
            "nodes",
            [
                {"_identity": 7, "id": 7, "name": "same"},
                {"_identity": 8, "id": 8, "name": "same"},
            ],
            {"_identity": "BIGINT", "id": "BIGINT", "name": "STRING"},
        )
        edges = Table(
            10,
            "edges",
            [
                {"_identity": 1, "src": 7, "dst": 8},
                {"_identity": 2, "src": 7, "dst": 8},
            ],
            {"_identity": "BIGINT", "src": "BIGINT", "dst": "BIGINT"},
            1,
            1,
        )
        source = Dataset((vertices, edges), {}, {}, "original")
        scaled = replicate(source, 3)
        for table in scaled.tables:
            independent = Table(
                table.group,
                table.name,
                table.records,
                table.types,
                table.source,
                table.target,
            )
            self.assertEqual(table.metadata(), independent.metadata())
        self.assertEqual(
            [row["id"] for row in scaled.table("nodes").records], [7, 8, 23, 24, 39, 40]
        )
        self.assertEqual(
            [(row["src"], row["dst"]) for row in scaled.table("edges").records],
            [(7, 8), (7, 8), (23, 24), (23, 24), (39, 40), (39, 40)],
        )
        self.assertEqual(len(source.table("nodes").records), 2)
        self.assertIs(replicate(source, 1), source)
        self.assertNotEqual(scaled.sha256, source.sha256)

    def test_argument_and_int64_envelopes(self) -> None:
        source = Dataset(
            (
                Table(
                    1,
                    "nodes",
                    [{"_identity": (1 << 63) - 1, "id": (1 << 63) - 1}],
                    {"_identity": "BIGINT", "id": "BIGINT"},
                ),
            ),
            {},
            {},
            "original",
        )
        for replicas in (0, 101, 2):
            with self.assertRaises(ValueError):
                replicate(source, replicas)


if __name__ == "__main__":
    unittest.main()
