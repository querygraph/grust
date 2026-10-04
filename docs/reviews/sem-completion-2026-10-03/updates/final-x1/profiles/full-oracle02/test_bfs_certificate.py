"""Independent signed-ID BFS witnesses and counterexamples; no engine or large input."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError

import bfs_certificate as c
import bfs_io as io
import bfs_models as m
import bfs_oracle as oracle

LOW, HIGH = -(2**63), 2**63 - 1
BIG = 2**53 + 1
IDS = [LOW, -7, -3, 0, 9, BIG, HIGH]
EDGES = [
    (0, -3),
    (0, 9),
    (-3, -7),
    (9, -7),
    (-7, LOW),
    (-3, BIG),
    (0, 0),
    (0, -3),
    (LOW, LOW),
]
# Independently enumerated paths: 0, { -3, 9 }, { -7, BIG }, { LOW }.
ANSWERS: list[tuple[int, int | None, int | None, int | None]] = [
    (LOW, 3, 3, -7),
    (-7, 2, 2, -3),
    (-3, 1, 1, 0),
    (0, 0, 0, 0),
    (9, 1, 1, 0),
    (BIG, 2, 2, -3),
    (HIGH, None, None, None),
]


def arrays(
    rows: list[tuple[int, int | None, int | None, int | None]],
) -> pa.RecordBatch:
    return pa.record_batch(
        [pa.array([row[i] for row in rows], type=pa.int64()) for i in range(4)],
        names=list(m.PROJECTED),
    )


def feed(
    state: c.State, rows: list[tuple[int, int | None, int | None, int | None]]
) -> None:
    batch = arrays(rows)
    values = [io.integers(batch, name, True) for name in m.PROJECTED]
    (
        (ids, valid_id),
        (distance, valid_distance),
        (hops, valid_hops),
        (parent, valid_parent),
    ) = values
    state.result_batch(
        ids, distance, hops, parent, valid_id, valid_distance, valid_hops, valid_parent
    )


def proof(
    rows: list[tuple[int, int | None, int | None, int | None]],
    edges: list[tuple[int, int]] | None = None,
    cap: int = 8,
    terminal: m.Terminal | None = None,
) -> m.Receipt:
    state = c.State(np.asarray(IDS, dtype=np.int64), 0)
    # Deliberately cross-batch duplicate/domain tracking rather than one giant batch.
    feed(state, rows[:3])
    feed(state, rows[3:])
    links = EDGES if edges is None else edges
    for start in range(0, len(links), 2):
        batch = links[start : start + 2]
        state.edge_batch(
            np.asarray([edge[0] for edge in batch], dtype=np.int64),
            np.asarray([edge[1] for edge in batch], dtype=np.int64),
        )
    receipt = m.Receipt(
        started_utc="test",
        configuration=m.Pin(path=Path("/test/config.json"), bytes=0, sha256="0" * 64),
    )
    state.finish(
        receipt,
        terminal or m.Terminal(levels=4, reached=6, phase=cap + 1, converged=1),
        cap,
        2,
    )
    return receipt


def config(output: Path) -> m.Config:
    placeholder = m.Pin(path=output.parent / "pin", bytes=0, sha256="0" * 64)
    return m.Config(
        dataset="tiny",
        vertices=[placeholder],
        edges=[placeholder],
        result=m.ResultSet(
            directory=output.parent / "raw",
            files={"part.parquet": m.Identity(bytes=0, sha256="0" * 64)},
        ),
        expected_vertices=7,
        expected_edges=9,
        source_id=0,
        max_levels=8,
        partitions=4,
        source_contract=m.SourceContract(
            repo=Path("/source"), head=m.SOURCE, tree="0" * 40, files=[placeholder]
        ),
        client_files=[placeholder],
        producer_evidence=[placeholder],
        helpers={
            name: placeholder
            for name in (
                "bfs_models.py",
                "bfs_io.py",
                "bfs_certificate.py",
                "bfs_oracle.py",
            )
        },
        output=output,
    )


class CertificateTests(unittest.TestCase):
    def test_original_weight_schema_preserved_for_unweighted_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "weighted-original-shape.parquet"
            table = pa.table(
                {
                    "src": pa.array([edge[0] for edge in EDGES], type=pa.int64()),
                    "dst": pa.array([edge[1] for edge in EDGES], type=pa.int64()),
                    "weight": pa.array(
                        [0.125 + index for index in range(len(EDGES))],
                        type=pa.float64(),
                    ),
                }
            )
            pq.write_table(table, path)
            original = io.pin(path, io.Deadline.after(5))
            plan = config(root / "audit").model_copy(
                update={
                    "edges": [original],
                    "edge_schema_profile": "original_weight3",
                    "limits": m.Limits(batch_rows=2),
                }
            )
            state = c.State(np.asarray(IDS, dtype=np.int64), 0, 2)
            feed(state, ANSWERS)
            receipt = m.Receipt(started_utc="test", configuration=original)
            oracle.edges(plan, state, receipt, io.Deadline.after(5))
            state.finish(
                receipt, m.Terminal(levels=4, reached=6, phase=9, converged=1), 8, 2
            )
            # Overall outcome also needs immutable source/output closure in verify().
            # This fixture exercises the complete edge and parent certificate only.
            self.assertTrue(receipt.full_domain_passed)
            self.assertTrue(receipt.parent_paths_and_minimum_parent_passed)
            self.assertTrue(receipt.all_edge_lower_bound_and_reachability_passed)
            self.assertTrue(receipt.terminal_empty_expansion_cap_passed)
            self.assertEqual(receipt.failures.total(), 0)
            self.assertTrue(receipt.all_original_edges_examined)
            physical = receipt.input_edge_physical_files[0]
            self.assertEqual(physical.fields, ["src", "dst", "weight"])
            self.assertEqual(physical.types, ["int64", "int64", "double"])
            self.assertEqual(physical.examined_columns, ["src", "dst"])
            self.assertEqual(physical.deliberately_unused_columns, ["weight"])
            self.assertEqual(physical.rows_examined, len(EDGES))
            self.assertEqual(physical.input, original)
            self.assertEqual(io.pin(path, io.Deadline.after(5)), original)

    def test_edge_profiles_reject_missing_extra_and_wrong_physical_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "edges.parquet"
            tiny = config(root / "audit")
            original = tiny.model_copy(
                update={"edge_schema_profile": "original_weight3"}
            )
            endpoints = {
                "src": pa.array([0], type=pa.int64()),
                "dst": pa.array([0], type=pa.int64()),
            }
            pq.write_table(pa.table(endpoints), path)
            self.assertEqual(
                io.edge_parquet(path, tiny).schema_arrow.names, ["src", "dst"]
            )
            with self.assertRaisesRegex(ValueError, "complete physical edge"):
                io.edge_parquet(path, original)
            for bad in [
                {**endpoints, "weight": pa.array([1], type=pa.float32())},
                {
                    **endpoints,
                    "weight": pa.array([1], type=pa.float64()),
                    "extra": pa.array([1]),
                },
                {
                    **endpoints,
                    "src": pa.array([0.0], type=pa.float64()),
                    "weight": pa.array([1], type=pa.float64()),
                },
            ]:
                pq.write_table(pa.table(bad), path)
                with self.assertRaises(ValueError):
                    io.edge_parquet(path, original)
            pq.write_table(
                pa.table({**endpoints, "weight": pa.array([1], type=pa.float64())}),
                path,
            )
            with self.assertRaisesRegex(ValueError, "complete physical edge"):
                io.edge_parquet(path, tiny)
            self.assertEqual(
                io.edge_parquet(path, original).schema_arrow.names,
                ["src", "dst", "weight"],
            )

    def test_original_dataset_requires_explicit_retained_weight_profile(self) -> None:
        data = config(Path("/tmp/schema-test/audit")).model_dump(mode="json")
        data.update(
            dataset="graph500-generated-scale24",
            expected_vertices=16777216,
            expected_edges=268435456,
            source_id=13507776,
            max_levels=8,
        )
        with self.assertRaisesRegex(ValidationError, "retained weight profile"):
            m.Config.model_validate_json(json.dumps(data))
        data["edge_schema_profile"] = "original_weight3"
        self.assertEqual(
            m.Config.model_validate_json(json.dumps(data)).edge_schema_profile,
            "original_weight3",
        )

    def test_verified_identity_domain_direct_lookup_and_bounds(self) -> None:
        state = c.State(np.arange(4, dtype=np.int64), 0, 2)
        self.assertTrue(state.identity_domain)
        feed(state, [(0, 0, 0, 0), (1, 1, 1, 0), (2, 2, 2, 1), (3, None, None, None)])
        state.edge_batch(
            np.asarray([0, 1, 0], dtype=np.int64), np.asarray([1, 2, 1], dtype=np.int64)
        )
        receipt = m.Receipt(
            started_utc="test",
            configuration=m.Pin(path=Path("/test/config"), bytes=0, sha256="0" * 64),
        )
        state.finish(
            receipt, m.Terminal(levels=3, reached=3, phase=9, converged=1), 8, 2
        )
        self.assertEqual(receipt.failures.total(), 0)
        self.assertTrue(receipt.identity_domain_verified)
        for endpoint in (LOW, -1, 4, HIGH):
            with self.assertRaisesRegex(ValueError, "endpoint outside"):
                state.edge_batch(
                    np.asarray([0], dtype=np.int64),
                    np.asarray([endpoint], dtype=np.int64),
                )

    def test_full_signed_highbit_duplicates_loops_and_isolate(self) -> None:
        result = proof(ANSWERS)
        self.assertEqual(result.failures.total(), 0)
        self.assertTrue(result.full_domain_passed)
        self.assertTrue(result.parent_paths_and_minimum_parent_passed)
        self.assertTrue(result.all_edge_lower_bound_and_reachability_passed)
        self.assertTrue(result.terminal_empty_expansion_cap_passed)
        self.assertEqual(result.full_array_bytes, 34 * len(IDS))

    def test_original_arc_orientation_reversal_preserves_undirected_answer(
        self,
    ) -> None:
        result = proof(list(reversed(ANSWERS)), [(v, u) for u, v in EDGES])
        self.assertEqual(result.failures.total(), 0)

    def test_wrong_distance_and_hops(self) -> None:
        rows = list(ANSWERS)
        rows[1] = (-7, 4, 3, -3)
        result = proof(rows)
        self.assertGreater(result.failures.distance_hops, 0)
        self.assertGreater(result.failures.minimum_parent, 0)
        self.assertGreater(result.failures.edge_level_gap, 0)

    def test_valid_edge_nonminimum_signed_parent_is_rejected(self) -> None:
        rows = list(ANSWERS)
        rows[1] = (-7, 2, 2, 9)  # A valid predecessor, but signed minimum is -3.
        self.assertEqual(proof(rows).failures.minimum_parent, 1)

    def test_unreachable_mixed_nulls_are_rejected(self) -> None:
        rows = list(ANSWERS)
        rows[-1] = (HIGH, None, 0, None)
        self.assertEqual(proof(rows).failures.null_tuple, 1)

    def test_omitted_reachable_component_detected_by_original_edges(self) -> None:
        rows = list(ANSWERS)
        rows[0] = (LOW, None, None, None)
        result = proof(rows)
        self.assertGreater(result.failures.edge_reachability_closure, 0)

    def test_fabricated_reached_isolate_has_no_rooted_parent_path(self) -> None:
        rows = list(ANSWERS)
        rows[-1] = (HIGH, 1, 1, 0)
        self.assertEqual(proof(rows).failures.minimum_parent, 1)

    def test_cross_batch_duplicate_unknown_and_missing_domain(self) -> None:
        result = proof([*ANSWERS[:-1], ANSWERS[2], (123, None, None, None)])
        self.assertEqual(result.failures.duplicate_rows, 1)
        self.assertEqual(result.failures.unknown_ids, 1)
        self.assertEqual(result.failures.missing_ids, 1)
        self.assertFalse(result.full_domain_passed)

    def test_source_self_parent_and_unique_zero(self) -> None:
        rows = list(ANSWERS)
        rows[3] = (0, 0, 0, -3)
        rows[2] = (-3, 0, 0, 0)
        result = proof(rows)
        self.assertEqual(result.failures.source_tuple, 1)
        self.assertEqual(result.failures.non_source_zero, 1)

    def test_empty_expansion_required_and_cap_distinct(self) -> None:
        result = proof(ANSWERS, cap=3)
        self.assertEqual(result.failures.total(), 0)
        self.assertEqual(result.computed_terminal_levels, 4)
        self.assertFalse(result.terminal_empty_expansion_cap_passed)
        result = proof(
            ANSWERS, terminal=m.Terminal(levels=3, reached=6, phase=9, converged=1)
        )
        self.assertFalse(result.terminal_empty_expansion_cap_passed)

    def test_max_signed_id_can_be_a_predecessor_not_an_absent_sentinel(self) -> None:
        state = c.State(np.asarray([LOW, -3, HIGH], dtype=np.int64), HIGH)
        feed(state, [(LOW, None, None, None), (-3, 1, 1, HIGH), (HIGH, 0, 0, HIGH)])
        state.edge_batch(
            np.asarray([HIGH], dtype=np.int64), np.asarray([-3], dtype=np.int64)
        )
        receipt = m.Receipt(
            started_utc="test",
            configuration=m.Pin(path=Path("/test/config"), bytes=0, sha256="0" * 64),
        )
        state.finish(
            receipt, m.Terminal(levels=2, reached=2, phase=9, converged=1), 8, 2
        )
        self.assertEqual(receipt.failures.total(), 0)

    def test_unknown_original_endpoint_refused(self) -> None:
        state = c.State(np.asarray(IDS, dtype=np.int64), 0)
        with self.assertRaisesRegex(ValueError, "endpoint outside"):
            state.edge_batch(
                np.asarray([0], dtype=np.int64), np.asarray([123], dtype=np.int64)
            )

    def test_physical_int64_highbit_and_nulls_never_go_through_float(self) -> None:
        batch = arrays(ANSWERS)
        parent, valid = io.integers(batch, "parent", True)
        self.assertEqual(int(parent[0]), -7)
        self.assertFalse(bool(valid[-1]))
        ids, _ = io.integers(batch, "id", False)
        self.assertEqual(int(ids[-2]), BIG)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "part.parquet"
            pq.write_table(pa.Table.from_batches([batch]), path)
            self.assertEqual(io.parquet(path, m.PROJECTED).metadata.num_rows, 7)
            wrong = pa.table({"id": pa.array([0.0], type=pa.float64())})
            pq.write_table(wrong, path)
            with self.assertRaisesRegex(ValueError, "signed Int64"):
                io.parquet(path, ("id",))

    def test_repeated_raw_terminal_and_stable_owner_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plan = config(Path(temporary) / "audit")
            fields = list(m.NATIVE)
            rows: list[list[int | None]] = []
            for answer in ANSWERS:
                owner = answer[0] % 4
                rows.append(
                    [
                        *answer,
                        owner,
                        owner % 2 + 1,
                        1000 + owner % 2,
                        10 + owner,
                        0,
                        9,
                        4,
                        6,
                        1,
                    ]
                )
            batch = pa.record_batch(
                [
                    pa.array([row[i] for row in rows], type=pa.int64())
                    for i in range(13)
                ],
                names=fields,
            )
            receipt = m.Receipt(started_utc="test", configuration=plan.vertices[0])
            owners: dict[int, m.Owner] = {}
            oracle.diagnostics(batch, plan, receipt, owners)
            self.assertEqual(receipt.failures.total(), 0)
            rows[0][11] = 5
            rows[1][6] = 999
            wrong = pa.record_batch(
                [
                    pa.array([row[i] for row in rows], type=pa.int64())
                    for i in range(13)
                ],
                names=fields,
            )
            oracle.diagnostics(wrong, plan, receipt, owners)
            self.assertGreater(receipt.failures.raw_diagnostics, 0)
            self.assertGreater(receipt.failures.owner_identity, 0)


if __name__ == "__main__":
    unittest.main()
