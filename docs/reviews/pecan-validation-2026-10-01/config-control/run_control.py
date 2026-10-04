#!/usr/bin/env python3
"""Two bounded local sessions isolating embedded PySpark package discovery."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback

os.environ['SPARK_CONNECT_MODE_ENABLED'] = '1'
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession

OUT = Path(__file__).resolve().parent
GATE = runpy.run_path(str(OUT.parent/'run_gate.py'))
BASE = GATE['BASE']
REPO = Path('/private/tmp/sail-certificate-parent-witness-gate')
HEAD = 'cab6bacc0ad0d1fc8b3070e9e4267e99751909fe'
TREE = 'cd73d093230153857de196abc17ea8e98464149b'
KEYS = ('spark.sql.timestampType', 'spark.sql.session.timeZone',
    'spark.sql.session.localRelationCacheThreshold', 'spark.sql.execution.pandas.convertToArrowArraySafely',
    'spark.sql.execution.pandas.inferPandasDictAsMap', 'spark.sql.pyspark.inferNestedDictAsStruct.enabled',
    'spark.sql.pyspark.legacy.inferArrayTypeFromFirstElement.enabled',
    'spark.sql.pyspark.legacy.inferMapTypeFromFirstPair.enabled', 'spark.sql.execution.arrow.useLargeVarTypes')


def client(endpoint, label):
    receipt = dict(outcome='FAILED', written_utc=BASE['utc'](), configs={}, explicit_conf_sets=[])
    spark = None
    try:
        # Invoke the exact pre-change fixture, without mocking or algorithm changes.
        fixture = runpy.run_path(str(REPO/'examples/extensions/graph-algorithms/tests/test_algorithms.py'))
        spark = SparkSession.builder.remote(endpoint).create()
        spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
        try:
            receipt['spark_version'] = spark.version
        except Exception as error:
            receipt['spark_version_error'] = repr(error)
        for key in KEYS:
            try:
                receipt['configs'][key] = dict(value=spark.conf.get(key))
            except Exception as error:
                receipt['configs'][key] = dict(error=repr(error))
        try:
            vertices, edges = fixture['frames'](spark)
        except Exception as error:
            receipt['fixture_error'] = repr(error)
            receipt['fixture_traceback'] = traceback.format_exc()
            assert label == 'without-server-client-path'
            assert 'configuration not found: spark.sql.execution.pandas.inferPandasDictAsMap' in str(error)
            receipt['baseline_failure_reproduced'] = True
        else:
            assert label == 'with-server-client-path'
            assert receipt['spark_version'] == '4.0.1'
            assert all('value' in row for row in receipt['configs'].values())
            assert spark.client.get_config_dict(*KEYS) == {k: v['value'] for k, v in receipt['configs'].items()}
            actual_vertices = sorted(row.id for row in vertices.collect())
            actual_edges = sorted((row.src, row.dst) for row in edges.collect())
            assert actual_vertices == sorted(fixture['IDS'])
            assert actual_edges == sorted(fixture['EDGES'])
            receipt.update(actual_vertices=actual_vertices, actual_edges=actual_edges, unchanged_fixture_exact_rows=True)
        receipt['outcome'] = 'PASS'
    except BaseException:
        receipt['error'] = traceback.format_exc()
    finally:
        if spark is not None:
            try:
                spark.stop()
                receipt['session_closed'] = True
            except BaseException:
                receipt.update(outcome='FAILED', cleanup_error=traceback.format_exc())
        BASE['save'](OUT/(label+'-client.json'), receipt)
    return 0 if receipt['outcome'] == 'PASS' else 1


def main():
    before = BASE['source_identity'](REPO, HEAD, TREE, 'exact')
    assert shutil.disk_usage(REPO).free >= 2 << 30
    assert BASE['sha'](GATE['BINARY']) == GATE['BINARY_SHA']
    assert not BASE['git'](REPO, 'diff', GATE['HOST_COMMIT'], '--', 'crates', 'Cargo.toml', 'Cargo.lock', '.cargo')
    paths = (Path(__file__), OUT.parent/'run_gate.py', GATE['BINARY'], BASE['PYTHON'].resolve(), BASE['PYLIB'])
    pins = {str(p): BASE['sha'](p) for p in paths}
    failures = {str(p): BASE['sha'](p) for p in (OUT.parent/'candidate-gate-03').iterdir() if p.is_file()}
    receipt = dict(outcome='FAILED', started_utc=BASE['utc'](), source=dict(head=HEAD, tree=TREE), pins=pins, cells=[])
    env = BASE['client_environment'](REPO/'examples/extensions/benchmarks', REPO)
    env['PYTHONPATH'] = os.pathsep.join(map(str, [REPO/'examples/extensions/graph-algorithms/src', BASE['CLIENT']]))
    env['CARGO_TARGET_DIR'] = str(OUT/'unused-target')
    server = child = None
    try:
        for label, server_path in [('without-server-client-path', None), ('with-server-client-path', str(BASE['CLIENT']))]:
            private = Path(tempfile.mkdtemp(prefix='pecan-config-control-'))
            staging = private/'staging'
            staging.mkdir()
            selected = dict(SAIL_MODE='local', SAIL_EXPERIMENTAL_EXTENSIONS='1', SAIL_EXPERIMENTAL_PROCESS_WORKERS='0',
                SAIL_EXECUTION__DEFAULT_PARALLELISM='2', SAIL_EXECUTION__COLLECT_STATISTICS='true',
                SAIL_RUNTIME__MEMORY_POOL__TYPE='greedy', SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(2 << 30),
                SAIL_GRAPH_UTILS_ROOT=staging.as_uri(), TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2', RUST_LOG='warn')
            server_env = dict(env, **selected)
            server_env.pop('PYTHONPATH', None)
            if server_path is not None:
                server_env['PYTHONPATH'] = server_path
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            record = dict(label=label, server_pythonpath=server_path, server_environment=selected)
            receipt['cells'].append(record)
            command = [str(GATE['BINARY']), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
            record['server_command'] = command
            with (OUT/(label+'-server.log')).open('x') as log:
                server = subprocess.Popen(command, cwd=private, env=server_env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record['server_pid_and_pgid'] = server.pid
            try:
                deadline = time.monotonic()+30
                while True:
                    assert server.poll() is None
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2):
                            break
                    except OSError:
                        assert time.monotonic() < deadline, 'server startup timeout'
                        time.sleep(.05)
                command = [str(BASE['PYTHON']), '-B', str(Path(__file__)), '--client', f'sc://127.0.0.1:{port}', '--label', label]
                record['client_command'] = command
                with (OUT/(label+'-client.log')).open('x') as log:
                    child = subprocess.Popen(command, cwd=private, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    record['client_returncode'] = child.wait(timeout=120)
                GATE['stop'](child)
                child = None
                assert record['client_returncode'] == 0, label
                record['client'] = json.loads((OUT/(label+'-client.json')).read_text())
            finally:
                GATE['stop'](server)
                record.update(server_reaped=True, server_group_absent=True, returncode=server.returncode)
                server = None
        receipt['outcome'] = 'PASS_PINNED_BASELINE_AND_SERVER_CLIENT_DISCOVERY'
    except BaseException:
        receipt['error'] = traceback.format_exc()
    finally:
        try:
            for process in (child, server):
                if process is not None:
                    GATE['stop'](process)
            assert before == BASE['source_identity'](REPO, HEAD, TREE, 'exact')
            assert pins == {p: BASE['sha'](p) for p in pins}
            assert failures == {str(p): BASE['sha'](p) for p in (OUT.parent/'candidate-gate-03').iterdir() if p.is_file()}
            receipt.update(source_runtime_unchanged=True, original_failed_gate_unchanged=True)
        except BaseException:
            receipt.update(outcome='FAILED', guard_or_cleanup_error=traceback.format_exc())
        receipt.update(finished_utc=BASE['utc'](), files_sha256={p.name: BASE['sha'](p) for p in OUT.iterdir() if p.is_file()},
            scope='Two local 2-thread/2GiB server cells; original cab6 nonempty fixture creation/readback only, no graph algorithm, native build, remote host or performance measurement.')
        BASE['save'](OUT/'receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('outcome', 'source_runtime_unchanged')}, indent=2))
    return 0 if receipt['outcome'].startswith('PASS_') else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--client')
    parser.add_argument('--label')
    args = parser.parse_args()
    raise SystemExit(client(args.client, args.label) if args.client else main())
