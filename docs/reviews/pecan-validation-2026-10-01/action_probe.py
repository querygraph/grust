"""One tiny real-engine validation-mode comparison on a supplied Connect endpoint.

Preparation only until invoked by the coordinator. Starts no server/container.
Records forwarded ExecutePlan calls and DataFrame.count call sites, not scanned
bytes, jobs or wall-time performance. Both modes must match the same exact
four-vertex oracle. Input snapshots, writes and cleanup still execute normally.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from urllib.parse import urlsplit

os.environ['SPARK_CONNECT_MODE_ENABLED'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import GraphAlgorithms
import pyspark_pecan

IDS = [-7, 42, 99, 1099511627776]
EDGES = [(-7, 42, 0.0), (42, 99, 1.0), (-7, 99, 1.0)]
EXPECTED = [(-7, 0.0, 0, -7), (42, 0.0, 1, -7), (99, 1.0, 1, -7),
            (1099511627776, None, None, None)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def source_inventory(repo):
    package = repo / 'examples/extensions/graph-algorithms/src/pyspark_pecan'
    rows = []
    for path in sorted(package.rglob('*.py')):
        require(not path.is_symlink(), 'symlink in package')
        data = path.read_bytes()
        rows.append(dict(path=str(path.relative_to(package)), bytes=len(data), sha256=sha(data)))
    require(rows, 'empty package source')
    return dict(files=rows, sha256=sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()))


def write(path, value):
    with path.open('x') as stream:
        json.dump(dict(recorded_utc=datetime.now(timezone.utc).isoformat(), **value), stream, indent=2)
        stream.write('\n')


class Trace:
    def __init__(self, spark, package, output):
        self.spark, self.package, self.output = spark, package, output
        self.mode, self.phase, self.count_id = None, 'setup', None
        self.events = []
        self.stream = None

    def sites(self):
        sites = []
        for frame in inspect.stack(context=1)[2:]:
            path = Path(frame.filename)
            if path.is_relative_to(self.package):
                sites.append(dict(path=str(path.relative_to(self.package)), function=frame.function,
                                  line=frame.lineno, source=''.join(frame.code_context or []).strip()))
        return sites

    def emit(self, kind, **values):
        row = dict(index=len(self.events), kind=kind, validate=self.mode, phase=self.phase, **values)
        self.events.append(row)
        self.stream.write(json.dumps(row) + '\n')
        self.stream.flush()
        return row['index']

    def __enter__(self):
        self.frame = DataFrame
        self.original_count = DataFrame.count
        self.original_execute = self.spark.client._stub.ExecutePlan
        self.stream = (self.output / 'actions.jsonl').open('x')

        def count(frame):
            # Preserve all other sessions exactly; this probe owns only one.
            if frame.sparkSession is not self.spark:
                return self.original_count(frame)
            previous = self.count_id
            self.count_id = self.emit('count', sites=self.sites())
            try:
                result = self.original_count(frame)
                self.emit('count_return', count_id=self.count_id, rows=result)
                return result
            except BaseException as error:
                self.emit('count_error', count_id=self.count_id, error=repr(error))
                raise
            finally:
                self.count_id = previous

        def execute(request, *args, **kwargs):
            plan = request.plan
            self.emit('ExecutePlan', count_id=self.count_id, sites=self.sites(),
                      plan_sha256=sha(plan.SerializeToString()),
                      plan_fields=[field.name for field, _ in plan.ListFields()])
            # Return the exact original iterator. No retry/response/metadata change.
            return self.original_execute(request, *args, **kwargs)

        self.count_wrapper, self.execute_wrapper = count, execute
        DataFrame.count = count
        self.spark.client._stub.ExecutePlan = execute
        return self

    def __exit__(self, *_):
        try:
            require(self.frame.count is self.count_wrapper and
                    self.spark.client._stub.ExecutePlan is self.execute_wrapper,
                    'instrumentation changed while running')
        finally:
            self.frame.count = self.original_count
            self.spark.client._stub.ExecutePlan = self.original_execute
            self.stream.close()


def summary(events, mode):
    rows = [r for r in events if r['validate'] is mode and r['phase'] == 'algorithm']
    counts = [r for r in rows if r['kind'] == 'count']
    by_site = Counter((r['sites'][0]['path'] + ':' + str(r['sites'][0]['line']) + ':' +
                       r['sites'][0]['function']) if r['sites'] else 'outside_package' for r in counts)
    return dict(count_calls=len(counts), count_calls_by_site=dict(sorted(by_site.items())),
                execute_plan_calls=sum(r['kind'] == 'ExecutePlan' for r in rows),
                boundary='public sssp call only; result oracle and cleanup separately tagged')


def prove_omitted_counts(events):
    """Pin the exact nine optional count actions in this DeltaStar fixture."""
    categories = {False: Counter(), True: Counter()}
    for event in events:
        if event['phase'] != 'algorithm' or event['kind'] != 'count':
            continue
        sites = event['sites']
        require(sites, 'count has no package callsite')
        first = sites[0]
        pair = (first['path'], first['function'])
        if pair == ('algorithms.py', '_validate_snapshot'):
            category = 'input_data_checks'
        elif pair == ('algorithms.py', '_snapshot'):
            category = 'vertex_cardinality'
        elif pair == ('staging.py', 'materialize'):
            category = 'postwrite_cardinality'
        elif pair == ('traversal.py', 'body') and 'source' in first['source']:
            category = 'source_membership'
        elif pair == ('traversal.py', 'body') and 'weight' in first['source']:
            category = 'weight_domain'
        else:
            raise RuntimeError('unexpected count callsite: ' + repr(first))
        categories[event['validate']][category] += 1
        forwarded = [r for r in events if r['kind'] == 'ExecutePlan' and r['count_id'] == event['index']]
        returned = [r for r in events if r['kind'] == 'count_return' and r['count_id'] == event['index']]
        require(len(forwarded) == len(returned) == 1,
                'count did not complete with exactly one forwarded ExecutePlan; retries not qualified')
    expected = dict(input_data_checks=5, vertex_cardinality=1, source_membership=1,
                    weight_domain=1, postwrite_cardinality=1)
    require(dict(categories[False]) == {} and dict(categories[True]) == expected,
            'optional count callsite inventory differs from expected nine versus zero')
    return dict(default=dict(categories[False]), checked=dict(categories[True]),
                scope='explicit count requests only; no physical bytes/scan or Spark job claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--package-sha256', required=True,
                        help='sha256 of source_inventory(repo) canonical files array')
    parser.add_argument('--remote', required=True)
    parser.add_argument('--runtime-label', required=True,
                        help='operator identity claim; this client cannot hash remote binary')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = dict(outcome='error', scope='real engine action counts, no performance/scanned-byte claim',
                   fixture=dict(ids=IDS, edges=EDGES, source=-7, directed=True, delta=1.0), cells=[])
    spark = trace = None
    before = None
    try:
        repo = args.repo.resolve(strict=True)
        package = repo / 'examples/extensions/graph-algorithms/src/pyspark_pecan'
        require(not args.output.resolve().is_relative_to(package), 'output inside source package')
        before = source_inventory(repo)
        require(before['sha256'] == args.package_sha256, 'package fingerprint mismatch')
        env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}
        head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, env=env).strip()
        require(head == args.source_commit, 'source HEAD mismatch')
        receipt.update(source_before=before, source_commit=head, runtime_claim=args.runtime_label,
                       interpreter=sys.version, helper_sha256=sha(Path(__file__).read_bytes()))
        endpoint = urlsplit(args.remote)
        require(endpoint.scheme == 'sc' and endpoint.hostname, 'expected sc:// endpoint')
        receipt['endpoint'] = dict(host=endpoint.hostname, port=endpoint.port)
        # The gate supplies PYTHONPATH before startup; never switch imported code.
        require(Path(pyspark_pecan.__file__).resolve().parent == package, 'wrong imported package')
        require(inspect.signature(GraphAlgorithms).parameters['validate'].default is False,
                'subject does not implement explicit validation default')
        receipt['packages'] = {name: importlib.metadata.version(name) for name in ['pyspark', 'pyarrow']}
        spark = SparkSession.builder.remote(args.remote).create()
        spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
        # SQL literals avoid local Arrow conversion/config discovery and infer no IDs.
        vertices = spark.sql('SELECT CAST(id AS BIGINT) id FROM VALUES (-7),(42),(99),(1099511627776) AS v(id)')
        edges = spark.sql('SELECT CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst, CAST(weight AS DOUBLE) weight '
                          'FROM VALUES (-7,42,0.0),(42,99,1.0),(-7,99,1.0) AS e(src,dst,weight)')
        with Trace(spark, package, args.output) as trace:
            for mode in [False, True]:
                trace.mode, trace.phase = mode, 'setup'
                cell = dict(validate=mode, outcome='error')
                receipt['cells'].append(cell)
                graph = GraphAlgorithms(spark, validate=mode, record_plans=False)
                handle = None
                try:
                    trace.phase = 'algorithm'
                    handle = graph.sssp(vertices, edges, source=-7, method='delta_star', directed=True,
                                        delta=1.0, max_iterations=10, partitions=2)
                    trace.phase = 'oracle'
                    values = [(r.id, r.distance, r.hops, r.parent) for r in
                              handle.frame.select('id', 'distance', 'hops', 'parent').collect()]
                    require(len(values) == len(IDS) and sorted(values) == EXPECTED,
                            'full four-vertex distance/parent/hops oracle mismatch')
                    require(handle.converged is True, 'not converged')
                    cell.update(outcome='passed', rows=sorted(values), iterations=handle.iterations,
                                converged=handle.converged)
                finally:
                    trace.phase = 'cleanup'
                    if handle is not None:
                        handle.close()
                    cell['actions'] = summary(trace.events, mode)
        fast, checked = receipt['cells']
        require(fast['iterations'] == checked['iterations'], 'validation mode changed iteration count')
        receipt['omitted_count_proof'] = prove_omitted_counts(trace.events)
        receipt['delta_checked_minus_default'] = {k: checked['actions'][k] - fast['actions'][k]
                                                   for k in ['count_calls', 'execute_plan_calls']}
        require(receipt['delta_checked_minus_default'] == dict(count_calls=9, execute_plan_calls=9),
                'ExecutePlan delta includes an unexplained action/retry difference')
        receipt['outcome'] = 'PASS_EXACT_ORACLE_AND_ACTION_REDUCTION'
    except BaseException:
        receipt['error'] = traceback.format_exc()
    finally:
        if spark is not None:
            try:
                spark.stop()
                receipt['session_closed'] = True
            except BaseException:
                receipt['cleanup_error'] = traceback.format_exc()
                receipt['outcome'] = 'error'
        if before is not None:
            try:
                receipt['source_after'] = source_inventory(args.repo.resolve())
                receipt['head_after'] = subprocess.check_output(
                    ['git', '-C', str(args.repo.resolve()), 'rev-parse', 'HEAD'], text=True,
                    env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}).strip()
                receipt['source_unchanged'] = (before == receipt['source_after'] and
                                               receipt['head_after'] == args.source_commit)
                if not receipt['source_unchanged']:
                    receipt['outcome'] = 'error'
            except BaseException:
                receipt['source_guard_error'] = traceback.format_exc()
                receipt['outcome'] = 'error'
        if (args.output / 'actions.jsonl').exists():
            receipt['actions_sha256'] = sha((args.output / 'actions.jsonl').read_bytes())
        write(args.output / 'receipt.json', receipt)
    return 0 if receipt['outcome'] == 'PASS_EXACT_ORACLE_AND_ACTION_REDUCTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
