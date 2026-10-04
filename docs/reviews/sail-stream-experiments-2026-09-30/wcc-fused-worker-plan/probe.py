"""Tiny real-worker production representative control; not a WCC/performance run."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import traceback


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            value.update(chunk)
    return value.hexdigest()


def fixture():
    high, low, maximum, minimum = 1 << 53, -(1 << 53), (1 << 63) - 1, -(1 << 63)
    return [(high + 10, high + 1), (high + 10, high), (high + 10, high + 1),
            (low + 10, low), (low - 1, low + 10),
            (maximum, maximum - 1), (maximum - 2, maximum),
            (minimum + 7, minimum + 1), (minimum, minimum + 7),
            (31, -7), (-7, 31), (-1, -1), (-100, 0), (0, -100)]


def oracle(edges):
    closed = {}
    for a, b in edges:
        closed.setdefault(a, {a}).add(b)
        closed.setdefault(b, {b}).add(a)
    return {vertex: min(neighbors) for vertex, neighbors in closed.items()}


def process_identity(binary, driver_pid):
    rows = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            executable = (proc / 'exe').resolve(strict=True)
            if executable != binary:
                continue
            status = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
            rows.append(dict(pid=int(proc.name), parent_pid=int(status['PPid']), executable=str(executable),
                             executable_sha256=digest(proc / 'exe')))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return dict(driver_pid=driver_pid, processes=rows,
                child_worker_pids=[row['pid'] for row in rows if row['parent_pid'] == driver_pid])


def main():
    config = json.loads(sys.argv[1])
    source, binary, output = map(Path, (config['container_repo'], config['container_sail_binary'], config['probe_output']))
    output.mkdir(parents=True, exist_ok=False)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['SPARK_CONNECT_MODE_ENABLED'] = '1'
    sys.path[:0] = [str(source / 'examples/extensions/benchmarks'),
                   str(source / 'examples/extensions/graph-algorithms/src')]
    from runtime import server, git, native_package_identity, package_versions
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect.client.retries import DefaultPolicy
    from pyspark.sql.types import LongType
    from pyspark_pecan import GraphUtils
    from pyspark_pecan.algorithms import physical_plan
    from pyspark_pecan.wcc_fused import representatives

    receipt = dict(started_utc=utc(), outcome='started', configuration=config,
                   scope='Actual unchanged production representatives(edges,1,0) under a two-worker runtime. Exact one-step closed-neighborhood oracle over active vertices only; no full WCC, certificate, scaling or timing claim.',
                   cases=[], cleanup_errors=[])
    spark = None

    def guard():
        assert git(source, 'rev-parse', 'HEAD') == config['harness_source_sha']
        assert git(source, 'status', '--porcelain') == ''
        assert digest(binary) == config['binary_sha256']
        for name, expected in config['source_files_sha256'].items():
            assert digest(source / name) == expected, name
        assert native_package_identity()['files_sha256'] == config['native_files_sha256']

    def timeout(*_):
        raise TimeoutError('tiny representative control exceeded its deadline')

    signal.signal(signal.SIGALRM, timeout)
    try:
        receipt['harness_source_sha'] = git(source, 'rev-parse', 'HEAD')
        guard()
        receipt.update(binary_sha256=digest(binary), packages=package_versions(),
                       native_identity=native_package_identity())
        settings = config['defaults']
        signal.alarm(config['probe_timeout_seconds'])
        with server(binary, output, 'process-cluster', settings['partitions'], settings['threads'],
                    settings['native_quota'], receipt['cleanup_errors'],
                    worker_task_slots=settings['worker_task_slots'], sail_pool_bytes=settings['sail_pool_bytes'],
                    http2_keepalive_timeout=120) as (endpoint, driver_pid):
            try:
                spark = SparkSession.builder.remote(endpoint).create()
                spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
                utils = GraphUtils(spark)
                assert 'axpb' in utils.capabilities
                receipt['graph_utils_capabilities'] = sorted(utils.capabilities)
                for name, edges in [('forward-input', fixture()), ('reversed-input', list(reversed(fixture())))]:
                    expected = oracle(edges)
                    frame = spark.createDataFrame(edges, 'src long,dst long').repartition(settings['partitions'])
                    result = representatives(frame, 1, 0)
                    plan = physical_plan(result)
                    (output / (name + '-plan.txt')).write_text(plan + '\n')
                    case = dict(name=name, edges=edges, expected=sorted(expected.items()), plan_sha256=digest(output / (name + '-plan.txt')))
                    receipt['cases'].append(case)
                    case['schema'] = result.schema.jsonValue()
                    assert result.columns == ['id', 'representative']
                    assert all(isinstance(field.dataType, LongType) for field in result.schema)
                    rows = [(row.id, row.representative) for row in result.collect()]
                    case['actual'] = sorted(rows)
                    assert len(rows) == len(expected) and len(dict(rows)) == len(rows)
                    assert dict(rows) == expected, case
                    case['process_identity'] = process_identity(binary.resolve(), driver_pid)
                    assert len(case['process_identity']['child_worker_pids']) == 2
                    assert all(row['executable_sha256'] == config['binary_sha256'] for row in case['process_identity']['processes'])
                    case['outcome'] = 'passed'
            finally:
                signal.alarm(0)
                if spark is not None:
                    try:
                        spark.stop()
                    except BaseException as error:
                        receipt['cleanup_errors'].append(dict(operation='spark.stop', error=repr(error)))
                    spark = None
        assert not receipt['cleanup_errors'], receipt['cleanup_errors']
        guard()
        receipt['source_and_binary_unchanged'] = True
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='error', error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
        receipt['finished_utc'] = utc()
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(outcome=receipt['outcome'], output=str(output))))
    return 0 if receipt['outcome'] == 'passed' and not receipt['cleanup_errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
