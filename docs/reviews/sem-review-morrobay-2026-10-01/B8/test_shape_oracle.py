"""Independent small Parquet controls for B8 reference and full-output checks."""
from __future__ import annotations

import ast
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import prepare_shapes
import pyarrow as pa
import pyarrow.parquet as pq
import shape_oracle
import shape_reference
from shape_reference import COLUMNS, InputConfig, Shape, sha


def scalar_affine(vertex: int, a: int, b: int) -> int:
    """Independent polynomial product then long division; not the vector recipe."""
    pattern, coefficient = vertex & (2**64 - 1), a & (2**64 - 1)
    product = 0
    for bit in range(64):
        if pattern & (1 << bit):
            product ^= coefficient << bit
    polynomial = (1 << 64) | 0x1B
    while product.bit_length() > 64:
        product ^= polynomial << (product.bit_length() - 65)
    product ^= b & (2**64 - 1)
    return product if product < 2**63 else product - 2**64


class Controls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ids = [-(2**63), -9, 0, 1, 2, 7, 2**63 - 1]
        self.edges = [(-(2**63), -9), (-9, 0), (-9, 0), (0, -9), (1, 1), (2, 2**63 - 1), (2**63 - 1, 2)]
        self.vertices = self.root / 'vertices.parquet'
        self.edgefile = self.root / 'edges.parquet'
        pq.write_table(pa.table({'id': pa.array(self.ids[::-1], type=pa.int64())}), self.vertices)
        pq.write_table(pa.table({'source': pa.array([a for a, _ in self.edges], type=pa.int64()),
                                'target': pa.array([b for _, b in self.edges], type=pa.int64())}), self.edgefile)
        self.config = InputConfig(vertices=self.vertices, edges=self.edgefile, output=self.root / 'references',
                                  vertices_sha256=sha(self.vertices), edges_sha256=sha(self.edgefile))
        self.receipt = prepare_shapes.prepare(self.config)
        self.assertEqual(self.receipt.outcome, 'passed', self.receipt.error)
        self.receipt_hash = sha(self.config.output / 'receipt.json')
        a, b = shape_reference.splitmix_coefficients()
        hashed = {vertex: scalar_affine(vertex, a, b) for vertex in self.ids}
        self.expected: dict[Shape, list[tuple[int, int]]] = {
            'adjacency': sorted(set(self.edges + [(b, a) for a, b in self.edges])),
            'representatives': sorted((vertex, min([hashed[vertex]] + [hashed[b if a == vertex else a]
                for a, b in self.edges if a != b and vertex in (a, b)])) for vertex in self.ids
                if any(a != b and vertex in (a, b) for a, b in self.edges)),
            'min-label-initial-round': [(vertex, min([vertex] + [b if a == vertex else a
                for a, b in self.edges if vertex in (a, b)])) for vertex in self.ids]}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_output(self, shape: Shape, name: str, rows: list[tuple[int, int]], *,
                     dtype: pa.DataType | None = None, names: list[str] | None = None) -> Path:
        output = self.root / name
        output.mkdir()
        names = names or COLUMNS[shape]
        dtype = dtype or pa.int64()
        # Partition/order independence is exercised by deterministic shuffling
        # and three files, including empty-footer files when a shape is small.
        order = rows.copy()
        random.Random(817).shuffle(order)
        for partition in range(3):
            subset = order[partition::3]
            table = pa.table({names[0]: pa.array([row[0] for row in subset], type=dtype),
                              names[1]: pa.array([row[1] for row in subset], type=dtype)})
            pq.write_table(table, output / f'part-{partition}.parquet', row_group_size=2)
        (output / '_SUCCESS').write_bytes(b'')
        return output

    def reference(self, shape: Shape) -> shape_oracle.LoadedReference:
        return shape_oracle.load_shape_reference(self.config.output, shape, self.receipt_hash)

    def test_reference_exact_semantics_and_portable_rows(self) -> None:
        self.assertEqual(self.receipt.vertex_rows, len(self.ids))
        self.assertEqual(self.receipt.edge_rows, len(self.edges))
        self.assertEqual(self.receipt.isolated_vertices, 1)
        for shape in COLUMNS:
            loaded = self.reference(shape)
            self.assertEqual([tuple(row) for row in loaded.pairs.tolist()], self.expected[shape])
            self.assertEqual(loaded.artifact.identity.bytes, 16 * len(self.expected[shape]))
            self.assertEqual(loaded.artifact.columns, COLUMNS[shape])
        self.assertNotIn(1, {row[0] for row in self.expected['representatives']})
        self.assertNotIn(7, {row[0] for row in self.expected['representatives']})

    def test_independent_affine_extremes_and_random_patterns(self) -> None:
        a, b = shape_reference.splitmix_coefficients()
        self.assertEqual((a, b), (-4767286540954276203, 2949826092126892291))
        vertices = self.ids + [random.Random(seed).randrange(-(2**63), 2**63) for seed in range(40)]
        actual = shape_reference.affine_signed(np.array(vertices, dtype=np.int64), a, b)
        self.assertEqual(actual.tolist(), [scalar_affine(v, a, b) for v in vertices])

    def test_all_six_forms_full_raw_outputs(self) -> None:
        for shape in COLUMNS:
            for variant in ('union', 'array-explode'):
                output = self.write_output(shape, shape + '-' + variant, self.expected[shape])
                result = shape_oracle.verify_shape_output(output, self.reference(shape), shape)
                self.assertEqual(result.rows, len(self.expected[shape]))
                self.assertTrue(result.full_oracle)
                self.assertEqual(result.result_files, result.result_files_after)
                self.assertEqual(len(result.physical_schemas), 3)
                self.assertEqual([field.name for field in result.physical_schemas[0].fields], COLUMNS[shape])

    def test_missing_rows_rejected_all_shapes(self) -> None:
        for shape in COLUMNS:
            output = self.write_output(shape, shape + '-missing', self.expected[shape][:-1])
            with self.subTest(shape=shape), self.assertRaises(shape_oracle.Mismatch):
                shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_duplicates_rejected_all_shapes(self) -> None:
        for shape in COLUMNS:
            rows = self.expected[shape] + [self.expected[shape][0]]
            output = self.write_output(shape, shape + '-duplicate', rows)
            with self.subTest(shape=shape), self.assertRaises(shape_oracle.Mismatch):
                shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_wrong_raw_pair_or_value_rejected_all_shapes(self) -> None:
        for shape in COLUMNS:
            rows = self.expected[shape].copy()
            rows[0] = (rows[0][0], rows[0][1] ^ 1)
            output = self.write_output(shape, shape + '-wrong', rows)
            with self.subTest(shape=shape), self.assertRaises(shape_oracle.Mismatch):
                shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_extra_vertex_rejected(self) -> None:
        shape: Shape = 'min-label-initial-round'
        output = self.write_output(shape, 'extra-id', self.expected[shape] + [(10, 10)])
        with self.assertRaises(shape_oracle.Mismatch):
            shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_schema_type_and_order_preserved_without_adapter(self) -> None:
        shape: Shape = 'adjacency'
        cases: list[tuple[str, dict[str, Any]]] = [('type', {'dtype': pa.float64()}), ('order', {'names': ['dst', 'src']})]
        for name, options in cases:
            output = self.write_output(shape, name, [(1, 2), (2, 1)], **options)
            with self.subTest(name=name), self.assertRaises(shape_oracle.Mismatch):
                shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_null_and_symlink_rejected(self) -> None:
        shape: Shape = 'adjacency'
        output = self.root / 'null'
        output.mkdir()
        pq.write_table(pa.table({'src': pa.array([1], type=pa.int64()), 'dst': pa.array([None], type=pa.int64())}), output / 'part.parquet')
        with self.assertRaises(shape_oracle.Mismatch):
            shape_oracle.verify_shape_output(output, self.reference(shape), shape)
        output = self.write_output(shape, 'symlink', self.expected[shape])
        (output / 'bad').symlink_to(output / 'part-0.parquet')
        with self.assertRaises(shape_oracle.Mismatch):
            shape_oracle.verify_shape_output(output, self.reference(shape), shape)

    def test_reference_and_receipt_tampering_rejected(self) -> None:
        with self.assertRaises(ValueError):
            shape_oracle.load_shape_reference(self.config.output, 'adjacency', '0' * 64)
        artifact = self.config.output / self.receipt.artifacts['adjacency'].file
        artifact.write_bytes(artifact.read_bytes() + b'corrupt')
        with self.assertRaises(ValueError):
            self.reference('adjacency')

    def test_reference_directory_is_portable(self) -> None:
        relocated = self.root / 'relocated'
        shutil.copytree(self.config.output, relocated)
        reference = shape_oracle.load_shape_reference(relocated, 'adjacency', self.receipt_hash)
        self.assertEqual(reference.pairs.tolist(), [list(row) for row in self.expected['adjacency']])

    def test_mismatch_receipt_retains_raw_schema_and_fresh_id(self) -> None:
        shape: Shape = 'adjacency'
        output = self.write_output(shape, 'wrong-schema', [(1, 2)], names=['dst', 'src'])
        config = shape_oracle.CheckConfig(output=output, references=self.config.output, shape=shape, variant='union',
                                         reference_receipt_sha256=self.receipt_hash, receipt_output=self.root / 'check.json')
        result = shape_oracle.run_check(config)
        self.assertEqual(result.outcome, 'mismatch')
        self.assertIsNotNone(result.progress)
        assert result.progress is not None
        self.assertEqual([field.name for field in result.progress.physical_schemas[0].fields], ['dst', 'src'])
        self.assertEqual(json.loads(config.receipt_output.read_text())['outcome'], 'mismatch')
        with self.assertRaises(ValueError):
            shape_oracle.run_check(config)

    def test_reference_error_retained_and_output_namespace_not_reused(self) -> None:
        config = self.config.model_copy(update={'output': self.root / 'failed-reference', 'edges_sha256': '0' * 64})
        result = prepare_shapes.prepare(config)
        self.assertEqual(result.outcome, 'error')
        self.assertTrue((config.output / 'receipt.json').is_file())
        with self.assertRaises(FileExistsError):
            prepare_shapes.prepare(config)

    def test_empty_graph_and_all_isolate_graph(self) -> None:
        for name, ids in [('empty', []), ('isolates', [-2, 0, 5])]:
            vertices, edges = self.root / (name + '-v.parquet'), self.root / (name + '-e.parquet')
            pq.write_table(pa.table({'id': pa.array(ids, type=pa.int64())}), vertices)
            pq.write_table(pa.table({'source': pa.array([], type=pa.int64()), 'target': pa.array([], type=pa.int64())}), edges)
            config = InputConfig(vertices=vertices, edges=edges, output=self.root / (name + '-refs'),
                                 vertices_sha256=sha(vertices), edges_sha256=sha(edges))
            receipt = prepare_shapes.prepare(config)
            self.assertEqual(receipt.outcome, 'passed', receipt.error)
            for shape in COLUMNS:
                reference = shape_oracle.load_shape_reference(config.output, shape, sha(config.output / 'receipt.json'))
                rows = [(vertex, vertex) for vertex in ids] if shape == 'min-label-initial-round' else []
                output = self.write_output(shape, name + '-' + shape, rows)
                self.assertEqual(shape_oracle.verify_shape_output(output, reference, shape).rows, len(rows))

    def test_chunk_boundary_dedup_and_owned_scratch_removal(self) -> None:
        output = self.root / 'chunked'
        output.mkdir()
        with mock.patch.object(shape_reference, 'BATCH_ROWS', 2):
            artifact = shape_reference.write_adjacency_reference(output, self.edgefile, len(self.edges))
        rows = np.fromfile(output / artifact.file, dtype='<i8').reshape((-1, 2)).tolist()
        self.assertEqual(rows, [list(row) for row in self.expected['adjacency']])
        self.assertFalse((output / 'adjacency-scratch.i64le').exists())
        self.assertIsNotNone(artifact.construction)
        assert artifact.construction is not None
        self.assertGreaterEqual(artifact.construction.quicksort_seconds, 0)

    def test_interrupted_scratch_is_retained(self) -> None:
        output = self.root / 'interrupted-sort'
        output.mkdir()
        with mock.patch.object(shape_reference, 'edge_batches', side_effect=InterruptedError('retained attempt')), self.assertRaises(InterruptedError):
            shape_reference.write_adjacency_reference(output, self.edgefile, len(self.edges))
        self.assertTrue((output / 'adjacency-scratch.i64le').is_file())

    def test_reference_ordering_checked_across_bounded_chunks(self) -> None:
        for shape in COLUMNS:
            output = self.root / (shape + '-order')
            output.mkdir()
            rows = np.array(self.expected[shape], dtype=np.int64)
            artifact = shape_reference.write_pairs(output, shape, rows)
            with mock.patch.object(shape_reference, 'BATCH_ROWS', 2):
                self.assertEqual(shape_reference.load_pairs(output / 'receipt.json', artifact, shape).tolist(), rows.tolist())
                rows[3] = rows[2]
                output = self.root / (shape + '-order-corrupt')
                output.mkdir()
                artifact = shape_reference.write_pairs(output, shape, rows)
                with self.subTest(shape=shape), self.assertRaises(ValueError):
                    shape_reference.load_pairs(output / 'receipt.json', artifact, shape)

    def test_actual_footer_and_bitmap_memory_models(self) -> None:
        self.assertIsNotNone(self.receipt.admission)
        assert self.receipt.admission is not None
        self.assertEqual(self.receipt.admission.edge_rows, len(self.edges))
        self.assertEqual(self.receipt.admission.vertex_rows, len(self.ids))
        self.assertLess(self.receipt.admission.estimated_memory_bytes, 32 * 2**30)
        output = self.write_output('adjacency', 'memory-oracle', self.expected['adjacency'])
        correctness = shape_oracle.verify_shape_output(output, self.reference('adjacency'), 'adjacency')
        self.assertEqual(correctness.memory_admission.seen_bitmap_bytes, len(self.expected['adjacency']))
        self.assertEqual(correctness.memory_admission.batch_rows, 65536)

    def test_typed_definitions_without_engine_imports(self) -> None:
        for name in ('shape_reference.py', 'prepare_shapes.py', 'shape_oracle.py', 'test_shape_oracle.py'):
            path = Path(__file__).with_name(name)
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertIsNotNone(node.returns, node.name)
                    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                        if arg.arg not in ('self', 'cls'):
                            self.assertIsNotNone(arg.annotation, node.name)
                    self.assertFalse(any(isinstance(child, (ast.Import, ast.ImportFrom)) for child in ast.walk(node)))
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.split('.')[0] in ('runtime', 'pyspark', 'pyspark_pecan') for alias in node.names))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], ('runtime', 'pyspark', 'pyspark_pecan'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
