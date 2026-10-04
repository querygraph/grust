"""Exact baseline/integrated DeltaStar actions on an operator-supplied local server.

One fresh client process per source package. Records forwarded requests, not
physical scans, jobs, bytes or performance. Starts no server or container.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from types import TracebackType
from typing import Any, TextIO
import traceback
from urllib.parse import urlsplit

os.environ['SPARK_CONNECT_MODE_ENABLED'] = '1'
sys.dont_write_bytecode = True

from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import GraphAlgorithms
import pyspark_pecan

IDS = [-7, 42, 99, 1099511627776]
EXPECTED = [(-7, 0.0, 0, -7), (42, 0.0, 1, -7), (99, 1.0, 1, -7), (1099511627776, None, None, None)]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(ok: object, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def write(path: Path, value: dict[str, Any]) -> None:
    with path.open('x') as stream:
        json.dump(dict(recorded_utc=datetime.now(timezone.utc).isoformat(), **value), stream, indent=2, allow_nan=False)
        stream.write('\n')


def source_inventory(repo: Path) -> dict[str, Any]:
    package = repo/'examples/extensions/graph-algorithms/src/pyspark_pecan'
    rows = []
    for path in sorted(package.rglob('*.py')):
        require(not path.is_symlink(), 'package symlink')
        data = path.read_bytes()
        rows.append(dict(path=str(path.relative_to(package)), bytes=len(data), sha256=sha(data)))
    require(rows, 'empty package')
    return dict(files=rows, sha256=sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()))


@dataclass(slots=True)
class Site:
    path: str
    function: str
    line: int
    source: str


@dataclass(slots=True)
class Action:
    index: int
    kind: str
    phase: str
    count_id: int | None
    sites: list[Site] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class Trace:
    def __init__(self, spark: SparkSession, package: Path, output: Path) -> None:
        self.spark, self.package, self.output = spark, package, output
        self.phase = 'setup'
        self.count_id: int | None = None
        self.events: list[Action] = []
        self.stream: TextIO | None = None

    def sites(self) -> list[Site]:
        result = []
        for frame in inspect.stack(context=1)[2:]:
            path = Path(frame.filename)
            if path.is_relative_to(self.package):
                result.append(Site(str(path.relative_to(self.package)), frame.function, frame.lineno,
                                   ''.join(frame.code_context or []).strip()))
        return result

    def emit(self, kind: str, sites: list[Site] | None = None, **details: Any) -> int:
        event = Action(len(self.events), kind, self.phase, self.count_id, sites or [], details)
        self.events.append(event)
        assert self.stream is not None
        self.stream.write(json.dumps(asdict(event))+'\n')
        self.stream.flush()
        return event.index

    def __enter__(self) -> Trace:
        self.original_count = DataFrame.count
        self.original_execute = self.spark.client._stub.ExecutePlan
        self.stream = (self.output/'actions.jsonl').open('x')

        def count(frame: DataFrame) -> int:
            if frame.sparkSession is not self.spark:
                return self.original_count(frame)
            previous = self.count_id
            self.count_id = self.emit('count', sites=self.sites())
            try:
                value = self.original_count(frame)
                self.emit('count_return', rows=value)
                return value
            except BaseException as error:
                self.emit('count_error', error=repr(error))
                raise
            finally:
                self.count_id = previous

        def execute(request: Any, *args: Any, **kwargs: Any) -> Any:
            self.emit('ExecutePlan', sites=self.sites(), plan_sha256=sha(request.plan.SerializeToString()),
                      plan_fields=[descriptor.name for descriptor, _ in request.plan.ListFields()])
            return self.original_execute(request, *args, **kwargs)

        self.count_wrapper, self.execute_wrapper = count, execute
        DataFrame.count = count
        self.spark.client._stub.ExecutePlan = execute
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None,
                 tb: TracebackType | None) -> None:
        try:
            require(DataFrame.count is self.count_wrapper and self.spark.client._stub.ExecutePlan is self.execute_wrapper,
                    'instrumentation changed')
        finally:
            DataFrame.count = self.original_count
            self.spark.client._stub.ExecutePlan = self.original_execute
            assert self.stream is not None
            self.stream.close()


def actions(events: list[Action]) -> dict[str, Any]:
    selected = [event for event in events if event.phase == 'algorithm']
    categories: Counter[str] = Counter()
    for event in selected:
        if event.kind != 'count':
            continue
        require(event.sites, 'count outside package')
        site = event.sites[0]
        if (site.path, site.function) == ('algorithms.py', '_snapshot'):
            category = 'vertex_cardinality' if site.source.startswith('return ') else 'input_data_checks'
        elif (site.path, site.function) == ('staging.py', 'materialize'):
            category = 'postwrite_cardinality'
        elif (site.path, site.function) == ('traversal_relaxation.py', 'materialize_weighted_relaxation'):
            category = 'distance_overflow'
        elif (site.path, site.function) == ('traversal.py', 'body') and 'source' in site.source:
            category = 'source_membership'
        elif (site.path, site.function) == ('traversal.py', 'body') and 'weight' in site.source:
            category = 'weight_domain'
        else:
            raise RuntimeError('unexpected count callsite: '+repr(site))
        categories[category] += 1
        forwarded = [row for row in events if row.kind == 'ExecutePlan' and row.count_id == event.index]
        returned = [row for row in events if row.kind == 'count_return' and row.count_id == event.index]
        require(len(forwarded) == len(returned) == 1, 'count did not forward/return exactly once')
    return dict(count_calls=sum(categories.values()), count_categories=dict(categories),
                execute_plan_calls=sum(event.kind == 'ExecutePlan' for event in selected),
                boundary='public SSSP call; excludes setup, exact oracle and cleanup')


def compare(baseline: Path, candidate: Path, output: Path) -> int:
    old, new = [json.loads((path/'receipt.json').read_text()) for path in (baseline, candidate)]
    require(all(r['outcome'] == 'PASS_EXACT_ORACLE' and r['session_closed'] and r['source_unchanged']
                and r['converged'] is True and r['spark_version'] == '4.0.1' for r in (old, new)), 'cell failed')
    require(old['label'] == 'baseline' and new['label'] == 'candidate', 'wrong comparison roles')
    require(old['runtime_claim'] == new['runtime_claim'] and old['endpoint'] == new['endpoint'], 'different runtime/endpoint')
    require(old['rows'] == new['rows'] == [list(row) for row in EXPECTED], 'oracle mismatch')
    require(old['iterations'] == new['iterations'] < 10, 'iteration/cap mismatch')
    expected = dict(input_data_checks=5, vertex_cardinality=1, source_membership=1, weight_domain=1,
                    postwrite_cardinality=1, distance_overflow=old['iterations'])
    require(old['actions']['count_categories'] == expected, 'baseline count categories differ')
    require(new['actions']['count_calls'] == 0 and new['actions']['count_categories'] == {}, 'candidate retained validation counts')
    removed = old['actions']['count_calls']-new['actions']['count_calls']
    execute_delta = old['actions']['execute_plan_calls']-new['actions']['execute_plan_calls']
    require(execute_delta == removed > 0, 'unexplained ExecutePlan change')
    write(output, dict(outcome='PASS_EXACT_ORACLE_AND_ACTION_REDUCTION', iterations=old['iterations'],
        removed_count_calls=removed, removed_execute_plan_calls=execute_delta, baseline=old['actions'], candidate=new['actions'],
        receipts_sha256={str(p/'receipt.json'): sha((p/'receipt.json').read_bytes()) for p in (baseline, candidate)},
        scope='One valid four-vertex fixture, same pinned local runtime and fresh clients; no timing/jobs/scanned-byte/cluster claim.'))
    return 0


def cell(args: argparse.Namespace) -> int:
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, Any] = dict(outcome='FAILED', label=args.label, runtime_claim=args.runtime_label)
    spark: SparkSession | None = None
    before = None
    try:
        repo = args.repo.resolve(strict=True)
        package = repo/'examples/extensions/graph-algorithms/src/pyspark_pecan'
        before = source_inventory(repo)
        require(before['sha256'] == args.package_sha256, 'package fingerprint mismatch')
        env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
        head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, env=env).strip()
        require(head == args.source_commit, 'HEAD mismatch')
        require(Path(pyspark_pecan.__file__).resolve().parent == package, 'wrong imported package')
        require('validate' not in inspect.signature(GraphAlgorithms).parameters, 'obsolete validation API')
        endpoint = urlsplit(args.remote)
        require(endpoint.scheme == 'sc' and endpoint.hostname, 'invalid endpoint')
        receipt.update(source_before=before, source_commit=head, helper_sha256=sha(Path(__file__).read_bytes()),
            endpoint=dict(host=endpoint.hostname, port=endpoint.port), interpreter=sys.version,
            packages={name: importlib.metadata.version(name) for name in ('pyspark', 'pyarrow')})
        spark = SparkSession.builder.remote(args.remote).create()
        spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
        receipt['spark_version'] = spark.version
        vertices = spark.sql('SELECT CAST(id AS BIGINT) id FROM VALUES (-7),(42),(99),(1099511627776) AS v(id)')
        edges = spark.sql('SELECT CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst, CAST(weight AS DOUBLE) weight '
                          'FROM VALUES (-7,42,0.0),(42,99,1.0),(-7,99,1.0) AS e(src,dst,weight)')
        with Trace(spark, package, output) as trace:
            graph = GraphAlgorithms(spark, record_plans=False)
            handle = None
            try:
                trace.phase = 'algorithm'
                handle = graph.sssp(vertices, edges, source=-7, method='delta_star', directed=True,
                                    delta=1.0, max_iterations=10, partitions=2)
                trace.phase = 'oracle'
                rows = sorted((r.id, r.distance, r.hops, r.parent) for r in handle.frame.select('id', 'distance', 'hops', 'parent').collect())
                require(rows == EXPECTED and handle.converged is True, 'exact oracle/convergence mismatch')
                receipt.update(rows=rows, converged=handle.converged, iterations=handle.iterations)
            finally:
                trace.phase = 'cleanup'
                if handle is not None:
                    handle.close()
        receipt['actions'] = actions(trace.events)
        receipt['outcome'] = 'PASS_EXACT_ORACLE'
    except BaseException:
        receipt['error'] = traceback.format_exc()
    finally:
        if spark is not None:
            try:
                spark.stop()
                receipt['session_closed'] = True
            except BaseException:
                receipt.update(outcome='FAILED', cleanup_error=traceback.format_exc())
        if before is not None:
            try:
                after = source_inventory(args.repo.resolve())
                head = subprocess.check_output(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], text=True,
                                               env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).strip()
                require(before == after and head == args.source_commit, 'source changed')
                receipt.update(source_after=after, source_unchanged=True)
            except BaseException:
                receipt.update(outcome='FAILED', source_guard_error=traceback.format_exc())
        if (output/'actions.jsonl').exists():
            receipt['actions_sha256'] = sha((output/'actions.jsonl').read_bytes())
        write(output/'receipt.json', receipt)
    return 0 if receipt['outcome'] == 'PASS_EXACT_ORACLE' else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--source-commit')
    parser.add_argument('--package-sha256')
    parser.add_argument('--remote')
    parser.add_argument('--runtime-label')
    parser.add_argument('--label', choices=['baseline', 'candidate'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    return compare(args.baseline, args.candidate, args.output) if args.compare else cell(args)


if __name__ == '__main__':
    raise SystemExit(main())
