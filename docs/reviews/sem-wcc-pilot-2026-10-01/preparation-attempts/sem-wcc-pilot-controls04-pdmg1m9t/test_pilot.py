"""Offline exact-oracle and delegated-instrumentation controls; no engine run."""
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).with_name('pilot.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PilotControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pairs = np.array([[1, 1], [3, 1], [8, 8], [13, 8], [21, 21]], dtype='<i8')
        self.ref = self.root / 'reference.i64le'
        self.pairs.tofile(self.ref)
        self.expected = p.oracle(self.ref, p.sha(self.ref), 5, 21)
        self.result = self.root / 'result'
        self.result.mkdir()

    def output(self, ids, labels, label_type=pa.int64()):
        pq.write_table(pa.table({'id': pa.array(ids, type=pa.int64()), 'component': pa.array(labels, type=label_type)}), self.result / 'part.parquet')

    def test_permuted_exact_mapping_including_isolate(self):
        self.output([21, 3, 13, 1, 8], [21, 1, 8, 1, 8])
        r = p.verify_output(self.result, self.expected, 5)
        self.assertEqual((r['rows'], r['unique'], r['membership_mismatches']), (5, 5, 0))

    def test_false_merge_fails_despite_edge_consistency(self):
        self.output([1, 3, 8, 13, 21], [1, 1, 1, 1, 1])
        with self.assertRaisesRegex(p.Mismatch, 'membership mismatch'):
            p.verify_output(self.result, self.expected, 5)

    def test_missing_duplicate_unknown_and_null_rows(self):
        for ids, labels in [([1, 3, 8, 13], [1, 1, 8, 8]), ([1, 3, 8, 13, 13], [1, 1, 8, 8, 8]),
                            ([1, 3, 8, 13, 20], [1, 1, 8, 8, 20]), ([1, 3, 8, 13, None], [1, 1, 8, 8, 21]),
                            ([1, 3, 8, 13, 21], [1, 1, 8, 8, None]), ([-1, 3, 8, 13, 21], [1, 1, 8, 8, 21])]:
            self.output(ids, labels)
            with self.subTest(ids=ids, labels=labels), self.assertRaises(p.Mismatch):
                p.verify_output(self.result, self.expected, 5)

    def test_wrong_schema_does_not_cast_to_pass(self):
        self.output([1, 3, 8, 13, 21], ['1', '1', '8', '8', '21'], pa.string())
        with self.assertRaisesRegex(p.Mismatch, 'exactly'):
            p.verify_output(self.result, self.expected, 5)

    def test_oracle_hash_and_truncation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hash/length'):
            p.oracle(self.ref, 'wrong', 5, 21)
        with self.assertRaisesRegex(ValueError, 'hash/length'):
            p.oracle(self.ref, p.sha(self.ref), 6, 21)

    def test_output_change_during_read_is_not_pass(self):
        self.output(self.pairs[:, 0], self.pairs[:, 1])
        original = p.inventory(self.result)
        changed = dict(original, **{'extra.parquet': dict(bytes=1, sha256='changed')})
        with patch.object(p, 'inventory', side_effect=[original, changed]), self.assertRaisesRegex(ValueError, 'changed'):
            p.verify_output(self.result, self.expected, 5)

    def test_duplicate_across_files_rejected(self):
        self.output(self.pairs[:, 0], self.pairs[:, 1])
        pq.write_table(pa.table({'id': pa.array([21], type=pa.int64()), 'component': pa.array([21], type=pa.int64())}), self.result / 'part2.parquet')
        with self.assertRaisesRegex(p.Mismatch, 'duplicate'):
            p.verify_output(self.result, self.expected, 5)

    def test_instrumentation_delegates_and_restores_even_on_failure(self):
        calls = []
        class Run:
            def materialize(self, value):
                calls.append(value)
                return value
        def snapshot(run, fail=False):
            run.materialize('vertices')
            run.materialize('edges')
            calls.append('validation')
            if fail:
                raise ValueError('original failure')
            return 'original result'
        module = SimpleNamespace(_check_input_schema=lambda: calls.append('schema'), _snapshot=snapshot, StagingRun=Run)
        original = (module._check_input_schema, module._snapshot, Run.materialize)
        for fail in [False, True]:
            calls.clear()
            r = {}
            if fail:
                with self.assertRaisesRegex(ValueError, 'original failure'), p.input_timers(module, r):
                    module._check_input_schema()
                    module._snapshot(Run(), fail=True)
            else:
                with p.input_timers(module, r):
                    module._check_input_schema()
                    self.assertEqual(module._snapshot(Run()), 'original result')
            self.assertEqual(calls, ['schema', 'vertices', 'edges', 'validation'])
            self.assertEqual((module._check_input_schema, module._snapshot, Run.materialize), original)
            self.assertEqual(len(r['input_snapshot_materialize_seconds']), 2)

    def test_round_counter_uses_differences_not_cumulative_average(self):
        events = [dict(kind=k, iteration=i, elapsed_seconds=t) for k, i, t in
                  [('iteration_start', 1, 10), ('iteration_end', 1, 14), ('iteration_start', 2, 15), ('iteration_end', 2, 18)]]
        r = p.round_summary(events, 23)
        self.assertEqual([x['seconds'] for x in r['completed_round_durations']], [4, 3])
        self.assertEqual((r['pre_first_round_seconds'], r['post_last_round_seconds']), (10, 5))
        self.assertEqual(p.round_summary([])['completed_round_durations'], [])

    def test_materialize_failure_restores_wrappers_and_checks_real_staging_root(self):
        calls = []
        class Run:
            path = (self.root / 'staging/run').as_uri()
            def materialize(self, frame):
                calls.append('original_write')
                if fail:
                    raise ValueError('original write failure')
                return 'unchanged'
        def snapshot(run, frame): return run.materialize(frame)
        module = SimpleNamespace(_check_input_schema=lambda: None, _snapshot=snapshot, StagingRun=Run,
                                 physical_plan=lambda _: self.fail('pilot must not add Explain RPC'))
        original = (module._snapshot, Run.materialize)
        for fail in (False, True):
            calls.clear()
            r = {}
            if fail:
                with self.assertRaisesRegex(ValueError, 'original write failure'), p.input_timers(module, r, self.root):
                    module._snapshot(Run(), object())
            else:
                with p.input_timers(module, r, self.root):
                    self.assertEqual(module._snapshot(Run(), object()), 'unchanged')
            self.assertEqual(calls, ['original_write'])
            self.assertEqual((module._snapshot, Run.materialize), original)
            self.assertTrue(r['graphutils_staging_root_verified'])
            self.assertEqual(len(r['input_snapshot_materialize_seconds']), 1)
        Run.path = (self.root / 'outside-watched-root').as_uri()
        with self.assertRaisesRegex(ValueError, 'outside watched'), p.input_timers(module, {}, self.root):
            module._snapshot(Run(), object())
        self.assertEqual((module._snapshot, Run.materialize), original)

    def test_failure_receipt_is_retained_and_not_passed(self):
        v, e, output = self.root / 'vertices.parquet', self.root / 'edges.parquet', self.root / 'cell'
        pq.write_table(pa.table({'id': pa.array([1], type=pa.int64())}), v)
        pq.write_table(pa.table({'source': pa.array([1], type=pa.int64()), 'target': pa.array([1], type=pa.int64())}), e)
        argv = ['pilot', '--repo', str(self.root), '--vertices', str(v), '--edges', str(e), '--reference', str(self.ref),
                '--output', str(output), '--mode', 'local', '--method', 'randomized_fused']
        original_exists = Path.exists
        def exists(path):
            return True if str(path) in ['/.dockerenv', '/proc/stat'] else original_exists(path)
        handlers = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM)}
        try:
            with patch.object(p.sys, 'argv', argv), patch.object(Path, 'exists', exists), patch.object(p, 'VERTICES_SHA', p.sha(v)), \
                 patch.object(p, 'EDGES_SHA', p.sha(e)), patch.object(p, 'REFERENCE_SHA', p.sha(self.ref)), patch.object(p, 'ROWS', 1), \
                 patch.object(p, 'EDGE_ROWS', 1), patch.object(p, 'execute', side_effect=p.Mismatch('injected membership failure')):
                self.assertEqual(p.main(), 1)
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
        r = json.loads((output / 'receipt.json').read_text())
        self.assertEqual(r['outcome'], 'mismatch')
        self.assertEqual(r['input_hashes_before'], r['input_hashes_after'])
        self.assertIn('injected membership failure', r['error'])


if __name__ == '__main__':
    unittest.main()
