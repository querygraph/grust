"""Offline relational/ownership controls; doubles cannot start an engine."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

SOURCE = Path('/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc')
PACKAGE = SOURCE / 'examples/extensions/graph-algorithms/src/pyspark_pecan'
HELPER = Path(__file__).with_name('engine_shapes.py')
Row = dict[str, Any]


def module(name: str) -> types.ModuleType:
    value = types.ModuleType(name)
    value.__path__ = []
    sys.modules[name] = value
    return value


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


@dataclass(slots=True)
class Expr:
    evaluate: Callable[[Row], Any]
    name: str
    aggregate: str | None = None

    def alias(self, name: str) -> Expr:
        return Expr(self.evaluate, name, self.aggregate)

    def cast(self, _type: str) -> Expr:
        return self

    def __eq__(self, other: object) -> Expr:  # type: ignore[override]
        assert isinstance(other, Expr)
        return Expr(lambda row: self.evaluate(row) == other.evaluate(row), 'equal')

    def __ne__(self, other: object) -> Expr:  # type: ignore[override]
        assert isinstance(other, Expr)
        return Expr(lambda row: self.evaluate(row) != other.evaluate(row), 'not-equal')

    def isNotNull(self) -> Expr:
        return Expr(lambda row: self.evaluate(row) is not None, 'not-null')


class Frame:
    def __init__(self, rows: list[Row], columns: list[str]) -> None:
        self.rows = rows
        self.columns = columns

    def __getattr__(self, name: str) -> Expr:
        if name not in self.columns:
            raise AttributeError(name)
        return column(name)

    def select(self, *values: str | Expr) -> Frame:
        expressions = [column(value) if isinstance(value, str) else value for value in values]
        exploded = [value for value in expressions if value.aggregate == 'explode']
        if exploded:
            assert len(expressions) == 1
            expression = exploded[0]
            rows = [{expression.name: value} for row in self.rows for value in expression.evaluate(row)]
        else:
            rows = [{expr.name: expr.evaluate(row) for expr in expressions} for row in self.rows]
        return Frame(rows, [expr.name for expr in expressions])

    def unionByName(self, other: Frame) -> Frame:
        assert self.columns == other.columns
        return Frame(self.rows + other.rows, self.columns)

    def distinct(self) -> Frame:
        unique = {json.dumps(row, sort_keys=True): row for row in self.rows}
        return Frame(list(unique.values()), self.columns)

    def where(self, condition: Expr) -> Frame:
        return Frame([row for row in self.rows if condition.evaluate(row)], self.columns)

    def join(self, other: Frame, condition: Expr, how: str = 'inner') -> Frame:
        assert not set(self.columns) & set(other.columns)
        rows: list[Row] = []
        for own in self.rows:
            matches = [own | row for row in other.rows if condition.evaluate(own | row)]
            rows.extend(matches if matches else [own | dict.fromkeys(other.columns)] if how == 'left' else [])
        return Frame(rows, self.columns + other.columns)

    def groupBy(self, key: str) -> Groups:
        return Groups(self, key)

    def repartition(self, partitions: int) -> Frame:
        assert partitions == 16
        return self

    def withColumn(self, name: str, expression: Expr) -> Frame:
        return Frame([row | {name: expression.evaluate(row)} for row in self.rows], self.columns + [name])

    def count(self) -> int:
        raise AssertionError('shape builder must not run count/validation')


@dataclass(slots=True)
class Groups:
    frame: Frame
    key: str

    def agg(self, expression: Expr) -> Frame:
        assert expression.aggregate == 'min'
        groups: dict[int, list[Row]] = {}
        for row in self.frame.rows:
            groups.setdefault(row[self.key], []).append(row)
        rows = [{self.key: key, expression.name: min(expression.evaluate(row) for row in values)}
                for key, values in groups.items()]
        return Frame(rows, [self.key, expression.name])


def column(name: str) -> Expr:
    def evaluate(row: Row) -> Any:
        value: Any = row
        for part in name.split('.'):
            value = value[part]
        return value
    return Expr(evaluate, name.split('.')[-1])


def literal(value: int) -> Expr:
    return Expr(lambda _row: value, 'literal')


def array(*expressions: Expr) -> Expr:
    return Expr(lambda row: [expr.evaluate(row) for expr in expressions], 'array')


def struct(*expressions: Expr) -> Expr:
    return Expr(lambda row: {expr.name: expr.evaluate(row) for expr in expressions}, 'struct')


def explode(expression: Expr) -> Expr:
    return Expr(expression.evaluate, 'explode', 'explode')


def minimum(name: str) -> Expr:
    return Expr(column(name).evaluate, 'min', 'min')


def least(*expressions: Expr) -> Expr:
    return Expr(lambda row: min(expr.evaluate(row) for expr in expressions), 'least')


def call_function(name: str, a: Expr, x: Expr, b: Expr) -> Expr:
    assert name == 'gf_axpb'
    return Expr(lambda row: WCC.signed(WCC.gf_axpb(a.evaluate(row), x.evaluate(row), b.evaluate(row))), 'axpb')


STUB_NAMES = ('pyspark', 'pyspark.sql', 'pyspark.sql.connect', 'pyspark.sql.connect.client',
              'pyspark.sql.connect.client.retries', 'pyspark.sql.connect.session',
              'pyspark.sql.connect.functions', 'pyspark_pecan', 'pyspark_pecan._contracts',
              'pyspark_pecan.types', 'pyspark_pecan.wcc_randomized', 'pyspark_pecan.algorithms',
              'pyspark_pecan.lifecycle', 'pyspark_pecan.staging', 'measurement', 'runtime')
SAVED_MODULES = {name: sys.modules.get(name) for name in STUB_NAMES}
for NAME in ('pyspark', 'pyspark.sql', 'pyspark.sql.connect', 'pyspark.sql.connect.client',
             'pyspark.sql.connect.client.retries', 'pyspark.sql.connect.session', 'pyspark_pecan'):
    module(NAME)
vars(sys.modules['pyspark.sql'])['DataFrame'] = Frame
vars(sys.modules['pyspark.sql.connect.client.retries'])['DefaultPolicy'] = object
vars(sys.modules['pyspark.sql.connect.session'])['SparkSession'] = object
FUNCTIONS = module('pyspark.sql.connect.functions')
for NAME, FUNCTION in [('col', column), ('lit', literal), ('array', array), ('struct', struct),
                       ('explode', explode), ('min', minimum), ('least', least), ('call_function', call_function)]:
    setattr(FUNCTIONS, NAME, FUNCTION)
vars(module('pyspark_pecan._contracts'))['ConvergenceError'] = RuntimeError
vars(module('pyspark_pecan.types'))['MASK'] = 2**64 - 1
vars(sys.modules['pyspark_pecan.types'])['ContractionStep'] = object
WCC = load('pyspark_pecan.wcc_randomized', PACKAGE / 'wcc_randomized.py')
ALG = module('pyspark_pecan.algorithms')
vars(ALG)['_snapshot'] = lambda _run, vertices, edges, *args, **kwargs: (vertices, edges, None)
vars(module('pyspark_pecan.lifecycle'))['GraphResult'] = object
vars(module('pyspark_pecan.staging'))['StagingRun'] = object
MEASUREMENT = module('measurement')
vars(MEASUREMENT)['cgroup_snapshot'] = lambda: dict.fromkeys(('memory.current', 'memory.peak', 'memory.max',
    'memory.swap.max', 'memory.events', 'cpu.max', 'cpu.stat'), '0')
vars(MEASUREMENT)['cpu_ticks'] = dict
vars(MEASUREMENT)['steal_fraction'] = lambda _before, _after: 0.0
RUNTIME = module('runtime')


def no_server(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError('offline controls cannot launch an engine')


vars(RUNTIME)['server'] = no_server
ENGINE = load('tested_engine_shapes', HELPER)

# The loaded engine holds its own stub references. Restore import names so a
# discovery run can load the real harness for supervisor controls afterwards.
for NAME, ORIGINAL in SAVED_MODULES.items():
    if ORIGINAL is None:
        sys.modules.pop(NAME, None)
    else:
        sys.modules[NAME] = ORIGINAL


class Controls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = {'repo': str(SOURCE), 'harness_repo': str(self.root / 'harness'), 'output': str(self.root / 'output'),
                    'vertices': str(self.root / 'v.parquet'), 'edges': str(self.root / 'e.parquet'),
                    'binary': str(self.root / 'binary'), 'shape': 'adjacency', 'variant': 'union'}
        ALG.__file__ = str(PACKAGE / 'algorithms.py')
        RUNTIME.__file__ = str(self.root / 'harness/examples/extensions/benchmarks/runtime.py')
        MEASUREMENT.__file__ = str(self.root / 'harness/examples/extensions/benchmarks/measurement.py')

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def journal(self) -> Any:
        config = ENGINE.ShapeConfig.model_validate_json(json.dumps(self.raw))
        config.output.mkdir()
        receipt = ENGINE.Receipt(config=config, started_utc=ENGINE.utc(), actual_method='offline', shape_scope='offline')
        return ENGINE.Journal(receipt, 0.0)

    def test_typed_definitions_no_local_imports_or_counts(self) -> None:
        for file in (HELPER, Path(__file__)):
            for node in ast.walk(ast.parse(file.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertIsNotNone(node.returns, node.name)
                    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                        if arg.arg not in ('self', 'cls'):
                            self.assertIsNotNone(arg.annotation, node.name)
                    self.assertFalse(any(isinstance(child, (ast.Import, ast.ImportFrom)) for child in ast.walk(node)))
        self.assertNotIn('.count(', HELPER.read_text())

    def test_config_exact_envelope(self) -> None:
        ENGINE.ShapeConfig.model_validate_json(json.dumps(self.raw))
        for key, value in [('mode', 'process-cluster'), ('partitions', 4), ('pool_bytes', 24 * 2**30),
                           ('native_quota', 0), ('shape', 'full-wcc'), ('variant', 'other'), ('vertices', 'relative')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                ENGINE.ShapeConfig.model_validate_json(json.dumps(self.raw | {key: value}))

    def test_adjacency_duplicates_reversals_and_self_loops(self) -> None:
        edges = Frame([{'src': -4, 'dst': 2}, {'src': -4, 'dst': 2}, {'src': 2, 'dst': -4},
                       {'src': 3, 'dst': 3}], ['src', 'dst'])
        expected = {(-4, 2), (2, -4), (3, 3)}
        for variant in ('union', 'array-explode'):
            rows = ENGINE.adjacency(edges, variant).rows
            self.assertEqual({(row['src'], row['dst']) for row in rows}, expected)
            self.assertEqual(len(rows), len(expected))

    def test_actual_coefficients_and_signed_representatives(self) -> None:
        a, b = WCC.SplitMix64(42).coefficients()
        self.assertEqual((a, b), (-4767286540954276203, 2949826092126892291))
        pairs = [(-4, 2), (2, 3), (2, 3), (3, -4), (6, 6)]
        edges = Frame([{'src': src, 'dst': dst} for src, dst in pairs if src != dst], ['src', 'dst'])
        hashed = {vertex: WCC.signed(WCC.gf_axpb(a, vertex, b)) for vertex in (-4, 2, 3)}
        expected = {vertex: min([hashed[vertex]] + [hashed[dst if vertex == src else src]
                    for src, dst in pairs if src != dst and vertex in (src, dst)]) for vertex in hashed}
        for variant in ('union', 'array-explode'):
            rows = ENGINE.representatives(edges, a, b, variant).rows
            self.assertEqual({row['id']: row['representative'] for row in rows}, expected)
            self.assertNotIn(6, {row['id'] for row in rows})

    def test_min_label_whole_update_keeps_isolates_and_signed_ids(self) -> None:
        ids = [-4, 2, 3, 20]
        pairs = [(-4, 2), (2, 3), (2, 3), (3, 3)]
        edges = Frame([{'src': src, 'dst': dst} for src, dst in pairs], ['src', 'dst'])
        neighbors = ENGINE.adjacency(edges, 'union')
        labels = Frame([{'id': vertex, 'component': vertex} for vertex in ids], ['id', 'component'])
        expected = {vertex: min([vertex] + [dst if src == vertex else src
                    for src, dst in pairs if vertex in (src, dst)]) for vertex in ids}
        for variant in ('union', 'array-explode'):
            rows = ENGINE.min_label_initial_round(labels, neighbors, variant).rows
            self.assertEqual({row['id']: row['component'] for row in rows}, expected)
            self.assertEqual(len(rows), len(ids))

    def test_empty_shapes(self) -> None:
        edges = Frame([], ['src', 'dst'])
        labels = Frame([], ['id', 'component'])
        for variant in ('union', 'array-explode'):
            self.assertEqual(ENGINE.adjacency(edges, variant).rows, [])
            self.assertEqual(ENGINE.representatives(edges, *WCC.SplitMix64(42).coefficients(), variant).rows, [])
            self.assertEqual(ENGINE.min_label_initial_round(labels, edges, variant).rows, [])

    def test_exact_module_origins(self) -> None:
        config = ENGINE.ShapeConfig.model_validate_json(json.dumps(self.raw))
        ENGINE.check_origins(config)
        with mock.patch.object(RUNTIME, '__file__', str(self.root / 'wrong.py')), self.assertRaises(RuntimeError):
            ENGINE.check_origins(config)

    def test_whole_update_preparation_plans_and_no_vertex_count(self) -> None:
        rows: list[list[Row]] = []
        for variant in ('union', 'array-explode'):
            config = ENGINE.ShapeConfig.model_validate_json(json.dumps(self.raw | {
                'shape': 'min-label-initial-round', 'variant': variant, 'output': str(self.root / variant)}))
            config.output.mkdir()
            receipt = ENGINE.Receipt(config=config, started_utc=ENGINE.utc(), actual_method='offline', shape_scope='offline')
            journal = ENGINE.Journal(receipt, 0.0)
            run = mock.Mock(partitions=16)
            prepared: list[list[Row]] = []
            def materialize(frame: Frame, captured: list[list[Row]] = prepared) -> tuple[str, Frame]:
                captured.append(frame.rows)
                return '/offline/stage', frame
            def finish(_path: str, frame: Frame, **_kwargs: Any) -> Any:
                return types.SimpleNamespace(frame=frame, method=None)
            def execute(vertices: Frame, edges: Frame, _partitions: int, _cancellation: Any,
                        body: Callable[..., Any], *, count_vertices: bool, active_run: Any = run) -> Any:
                self.assertFalse(count_vertices)
                return body(active_run, vertices, edges, None)
            run.materialize.side_effect = materialize
            run.finish.side_effect = finish
            graph = mock.Mock()
            graph._run.side_effect = execute
            vertices = Frame([{'id': -4}, {'id': 2}, {'id': 20}], ['id'])
            edges = Frame([{'src': -4, 'dst': 2}], ['src', 'dst'])
            with mock.patch.object(ALG, 'physical_plan', create=True, return_value='offline explain; not engine evidence'):
                handle = ENGINE.build_shape(graph, vertices, edges, config, journal)
            rows.append(handle.frame.rows)
            self.assertEqual(prepared[:2], [[{'src': -4, 'dst': 2}, {'src': 2, 'dst': -4}],
                                           [{'id': -4, 'component': -4}, {'id': 2, 'component': 2}, {'id': 20, 'component': 20}]])
            self.assertEqual([plan.relation for plan in receipt.plans], ['initial-adjacency', 'initial-labels', 'shape-result'])
            self.assertEqual(len(prepared), 3)
            for plan in receipt.plans:
                self.assertTrue((config.output / plan.file).is_file())
            self.assertTrue(all(any(phase.name == 'plan_' + plan.relation and phase.status == 'end' for phase in receipt.phases)
                                for plan in receipt.plans))
        self.assertEqual(sorted(rows[0], key=lambda row: row['id']), sorted(rows[1], key=lambda row: row['id']))

    def test_snapshot_hook_delegates_once_and_restores(self) -> None:
        journal = self.journal()
        original = ALG._snapshot
        frame = Frame([], ['id'])
        with mock.patch.object(ALG, '_snapshot', wraps=original) as delegate:
            with ENGINE.snapshot_phase(journal):
                ALG._snapshot(object(), frame, frame, count_vertices=False)
            self.assertIs(ALG._snapshot, delegate)
            delegate.assert_called_once()
        self.assertIs(ALG._snapshot, original)

    def test_cleanup_runs_even_if_journal_start_fails(self) -> None:
        journal = self.journal()
        sink = ENGINE.CleanupSink()
        action = mock.Mock()
        with mock.patch.object(ENGINE.Journal, 'mark', side_effect=OSError('journal unavailable')):
            ENGINE.cleanup(journal, sink, 'close', action)
        action.assert_called_once()
        self.assertEqual(sink.records[0].operation, 'close')

    def test_server_closed_if_post_enter_journal_write_fails(self) -> None:
        journal = self.journal()
        config = journal.receipt.config
        calls: list[str] = []
        @contextlib.contextmanager
        def server(*_args: Any, **_kwargs: Any) -> Iterator[tuple[str, int]]:
            calls.append('enter')
            try:
                yield 'offline-endpoint', 17
            finally:
                calls.append('exit')
        original = ENGINE.Journal.mark
        def fail_end(self: Any, phase: Any) -> None:
            if phase.name == 'server_startup' and phase.status == 'end':
                raise OSError('post-enter durable write failure')
            original(self, phase)
        sink = ENGINE.CleanupSink()
        with mock.patch.object(RUNTIME, 'server', side_effect=server), mock.patch.object(ENGINE.Journal, 'mark', fail_end), self.assertRaises(OSError):
            ENGINE.execute(config, journal, sink)
        self.assertEqual(calls, ['enter', 'exit'])

    def test_main_retains_payload_and_interruption(self) -> None:
        for name, outcome in [('empty', 'passed'), ('payload', 'cleanup_error'), ('timeout', 'timeout'), ('interrupt', 'interrupted')]:
            config = self.raw | {'output': str(self.root / name)}
            path = self.root / (name + '.json')
            path.write_text(json.dumps(config))
            def execute(config: Any, journal: Any, _sink: Any, case_name: str = name) -> None:
                directory = config.output / 'staging' / 'empty-directory'
                directory.mkdir(parents=True)
                journal.receipt.result_exported = True
                if case_name != 'empty':
                    (directory / 'partial.parquet').write_bytes(b'retained')
                if case_name == 'timeout':
                    raise TimeoutError('offline timeout')
                if case_name == 'interrupt':
                    raise InterruptedError('offline interruption')
            with self.subTest(name=name), mock.patch.object(ENGINE, 'execute', side_effect=execute), mock.patch.object(sys, 'argv', ['engine_shapes.py', '--config', str(path)]):
                code = ENGINE.main()
                receipt = json.loads((Path(config['output']) / 'engine-receipt.json').read_text())
                self.assertEqual(receipt['outcome'], outcome)
                self.assertEqual(code, 0 if outcome == 'passed' else 1)
                self.assertEqual(bool(receipt['staging_payload_after_shutdown']), name != 'empty')
        with mock.patch.object(sys, 'argv', ['engine_shapes.py', '--config', str(path)]), self.assertRaises(FileExistsError):
            ENGINE.main()


if __name__ == '__main__':
    unittest.main(verbosity=2)
