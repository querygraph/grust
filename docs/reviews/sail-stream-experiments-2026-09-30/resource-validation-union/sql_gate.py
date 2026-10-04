"""Exact detached-source Python/SQL gate for an explicitly pinned NEW Sail CLI.

No builds, installation, installed-Sail fallback, experimental extensions or
remote hosts. Fixtures remain private. This helper is not a benchmark.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

PYTHON = Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python')
PYHOME = Path('/Users/alexy/.local/share/uv/python/cpython-3.12.8-macos-aarch64-none')
PYLIB = PYHOME / 'lib/libpython3.12.dylib'
CLIENT = PYTHON.parent.parent / 'lib/python3.12/site-packages'
EXPECTED_UNIT = dict(tests=430, failures=0, errors=0, skipped=97)
EXPECTED_SQL = dict(tests=58, failures=0, errors=0, skipped=0)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args],
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=30)


def source_identity(repo, head, tree, mode):
    assert git(repo, 'rev-parse', 'HEAD').decode().strip() == head, 'HEAD mismatch'
    symbolic = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'],
                              capture_output=True, timeout=30)
    assert symbolic.returncode == 1, 'gate must be detached'
    assert git(repo, 'write-tree').decode().strip() == tree, 'index tree mismatch'
    assert not git(repo, 'diff', '--name-only'), 'unstaged tracked change'
    if mode == 'exact':
        assert git(repo, 'rev-parse', 'HEAD^{tree}').decode().strip() == tree
        assert not git(repo, 'diff', '--cached', '--name-only'), 'exact gate has staged changes'
    untracked = git(repo, 'ls-files', '--others', '--exclude-standard', '-z')
    assert not untracked, 'untracked nonignored source in gate'
    inventory = {}
    for entry in git(repo, 'ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1)
        permissions, blob, stage = meta.decode().split()
        assert stage == '0', 'unmerged index'
        path = repo / os.fsdecode(name)
        assert permissions != '160000', 'submodule needs explicit identity policy'
        content = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        inventory[os.fsdecode(name)] = dict(mode=permissions, blob=blob,
            working_sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
    index = Path(os.fsdecode(git(repo, 'rev-parse', '--git-path', 'index')).strip())
    if not index.is_absolute():
        index = repo / index
    return dict(head=head, tree=tree, mode=mode, index_sha256=sha(index), files=inventory)


def client_environment(bench, repo):
    env = {k: v for k, v in os.environ.items() if not k.startswith('SAIL_')
           and k not in ('PYTHONPATH', 'PYTHONHOME', 'DYLD_LIBRARY_PATH')}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHOME=str(PYHOME),
        DYLD_LIBRARY_PATH=str(PYHOME/'lib'), CARGO_INCREMENTAL='0', GIT_OPTIONAL_LOCKS='0',
        PATH=str(PYTHON.parent)+os.pathsep+env.get('PATH', os.defpath),
        PYTHONPATH=os.pathsep.join(map(str, [CLIENT, bench,
            repo/'examples/extensions/nutmeg/python',
            repo/'examples/extensions/graph-algorithms/src'])))
    return env


def server_environment(env):
    selected = dict(SAIL_MODE='local', SAIL_EXECUTION__DEFAULT_PARALLELISM='2',
        SAIL_EXECUTION__COLLECT_STATISTICS='true', TOKIO_WORKER_THREADS='2',
        RAYON_NUM_THREADS='2', RUST_LOG='warn')
    environment = dict(env, **selected)
    environment.pop('PYTHONPATH')
    return environment, selected


def interrupted(signum, _frame):
    raise InterruptedError('received signal '+str(signum))


def interpreter_probe():
    import encodings
    import importlib
    assert sys.version_info[:3] == (3, 12, 8), 'unexpected client CPython version'
    path_python = shutil.which('python3')
    assert path_python is not None and Path(path_python).resolve() == PYTHON.resolve(), \
        '/usr/bin/env python3 must select the pinned CPython interpreter'
    encoding_file = Path(encodings.__file__).resolve()
    assert encoding_file.is_relative_to(PYHOME/'lib/python3.12'), 'unexpected Python standard library'
    modules = {}
    for name in ('pyspark', 'pyarrow', 'numpy', 'grpc', 'pytest'):
        module = importlib.import_module(name)
        file = Path(module.__file__).resolve()
        modules[name] = dict(version=getattr(module, '__version__', None),
                             file=str(file), sha256=sha(file))
    print(json.dumps(dict(executable=sys.executable, real_executable=str(Path(sys.executable).resolve()),
        executable_sha256=sha(Path(sys.executable).resolve()), version=sys.version,
        path_python3=path_python, path_python3_real=str(Path(path_python).resolve()),
        path_python3_sha256=sha(Path(path_python).resolve()),
        stdlib_encodings_file=str(encoding_file), stdlib_encodings_sha256=sha(encoding_file),
        prefix=sys.prefix, base_prefix=sys.base_prefix, modules=modules), allow_nan=False))


def default_statistics_control(endpoint, private, output):
    import math
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pyspark.sql.connect.session import SparkSession
    from graph_cell import validate
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    private = Path(private)
    dataset = private/'default-statistics-dataset'
    dataset.mkdir()
    pq.write_table(pa.table({'id': [0, 1]}), dataset/'vertices.parquet')
    pq.write_table(pa.table({'src': [0, 1], 'dst': [1, 0]}), dataset/'edges.parquet')
    pq.write_table(pa.table({'id': [0, 1], 'pagerank': [.5, .5]}), dataset/'reference.parquet')
    spark = None
    result = dict(started_utc=utc(), scope='Actual new CLI; default-statistics Parquet read and both builtin PageRank policies; tiny local fixture only.', checks=[])
    try:
        spark = SparkSession.builder.remote(endpoint).create()
        for case, scores in [('mixed_nan_finite', [float('nan'), .5]), ('finite_fixed_point', [.5, .5])]:
            target = private/case
            target.mkdir()
            file = target/'part.parquet'
            pq.write_table(pa.table({'id': [0, 1], 'score': pa.array(scores, type=pa.float64()),
                'iterations': pa.array([1, 1], type=pa.int64()), 'converged': [True, True],
                'residual': [0., 0.]}), file)  # default write_statistics=True
            metadata = pq.read_metadata(file)
            stats = metadata.row_group(0).column(1).statistics
            assert stats is not None and stats.has_min_max and stats.min == stats.max == .5
            rows = spark.read.parquet(target.as_uri()).select('id', 'score').orderBy('id').collect()
            assert len(rows) == 2 and [r.id for r in rows] == [0, 1]
            assert rows[1].score == .5
            assert math.isnan(rows[0].score) if case == 'mixed_nan_finite' else rows[0].score == .5
            record = dict(case=case, file_sha256=sha(file), file_bytes=file.stat().st_size,
                footer_min=stats.min, footer_max=stats.max, writer=metadata.created_by,
                direct_read_nan_mask=[math.isnan(r.score) for r in rows], policies={})
            result['checks'].append(record)
            for policy in ('reference', 'certificate'):
                try:
                    proof = validate(spark, target, dataset, 'pagerank', 2, 1e-8, .85, 100,
                                     False, False, policy=policy)
                except AssertionError as error:
                    assert case == 'mixed_nan_finite' and 'invalid PageRank scores' in str(error), str(error)
                    record['policies'][policy] = dict(outcome='expected_rejection', error=str(error))
                else:
                    assert case == 'finite_fixed_point', 'mixed NaN/finite falsely accepted'
                    assert proof['rows'] == proof['unique_ids'] == 2 and proof['true_fixed_point_residual'] == 0
                    record['policies'][policy] = dict(outcome='passed', proof=proof)
        result['outcome'] = 'passed'
    except BaseException as error:
        result.update(outcome='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if spark is not None:
            try:
                spark.stop()
            except BaseException as error:
                result.update(outcome='failed_cleanup', cleanup_error=str(error))
        result['finished_utc'] = utc()
        save(output, result)
    assert result['outcome'] == 'passed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-tree', required=True)
    parser.add_argument('--mode', choices=['candidate', 'exact'], required=True)
    parser.add_argument('--sail-binary', '--binary', type=Path, required=True)
    parser.add_argument('--sail-sha256', '--binary-sha256', required=True)
    args = parser.parse_args()
    repo, output, binary = args.repo.resolve(), args.output.resolve(), args.sail_binary.resolve()
    assert repo not in output.parents and repo != output, 'output must be outside source'
    output.mkdir(exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='resource-validation-sql-'))
    receipt = dict(started_utc=utc(), expected_head=args.expected_head, expected_tree=args.expected_tree,
        mode=args.mode, private_fixtures=str(private), commands=[], driver_python=dict(executable=sys.executable,
            real_executable=str(Path(sys.executable).resolve()), version=sys.version),
        scope='New explicitly pinned Sail CLI built separately from union; builtin local SQL only. No installed-runtime fallback, experimental extension/native import requirement, cluster or performance verdict.')
    server = None
    before = pins = None
    bench = repo/'examples/extensions/benchmarks'
    env = client_environment(bench, repo)
    env['CARGO_TARGET_DIR'] = str(private/'unused-target')

    def run(command, label, environment=env):
        record = dict(label=label, command=list(map(str, command)), started_utc=utc())
        receipt['commands'].append(record)
        with (output/(label+'.log')).open('x') as log:
            try:
                process = subprocess.run(command, cwd=repo, env=environment, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=300)
                record['returncode'] = process.returncode
                process.check_returncode()
            finally:
                record['finished_utc'] = utc()

    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        assert sys.version_info[:3] == (3, 12, 8), 'gate driver must use pinned CPython 3.12.8'
        assert shutil.disk_usage(repo).free >= 1 << 30
        before = source_identity(repo, args.expected_head, args.expected_tree, args.mode)
        save(output/'source-before.json', before)
        assert binary.is_file() and os.access(binary, os.X_OK)
        assert len(args.sail_sha256) == 64 and sha(binary) == args.sail_sha256
        assert binary != Path('/Users/alexy/src/sail/.venvs/default/bin/sail').resolve(), 'installed fallback forbidden'
        pins = {str(p): sha(p) for p in [binary, PYTHON.resolve(), Path(sys.executable).resolve(),
                                        PYLIB, Path(__file__).resolve()]}
        receipt['runtime_and_interpreter_pins'] = pins
        run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--interpreter-probe'], 'client-before')
        receipt['client_before'] = json.loads((output/'client-before.log').read_text())
        run(['git', 'diff', '--check', 'HEAD'], 'diff-check')
        run([str(PYTHON), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(bench),
             '--junitxml='+str(output/'unit.xml'), '--basetemp='+str(private/'unit')], 'unit')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        endpoint = f'sc://127.0.0.1:{port}'
        server_env, selected_settings = server_environment(env)
        receipt['selected_server_environment'] = selected_settings
        command = [str(binary), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
        receipt['server_command'] = command
        with (output/'server.log').open('x') as log:
            server = subprocess.Popen(command, cwd=private, env=server_env, stdout=log, stderr=subprocess.STDOUT)
        receipt['server_pid'] = server.pid
        deadline = time.monotonic()+30
        while True:
            if server.poll() is not None:
                raise RuntimeError('SQL server exited at startup')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError('SQL server startup timeout')
                time.sleep(.05)
        sql_env = dict(env, SAIL_GRAPH_TEST_REMOTE=endpoint)
        run([str(PYTHON), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(bench/'test_pagerank_metadata.py'),
             str(bench/'test_wcc_certificate.py'), '--junitxml='+str(output/'sql.xml'),
             '--basetemp='+str(private/'sql')], 'sql', sql_env)
        run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--default-statistics-control', endpoint,
             str(private), str(output/'default-statistics.json')], 'default-statistics', sql_env)
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='failed', error_type=type(error).__name__, error=str(error))
    finally:
        # A cancelling parent may signal the entire group. Retain a receipt and
        # reap our directly owned server before allowing further interruption.
        for signum in handlers:
            signal.signal(signum, signal.SIG_IGN)
        if server is not None:
            try:
                if server.poll() is None:
                    server.terminate()
                else:
                    receipt.update(outcome='failed_server', unexpected_server_exit=server.returncode)
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)
                receipt.update(server_reaped=True, server_returncode=server.returncode)
            except BaseException as error:
                receipt.update(outcome='failed_cleanup', server_reaped=False, cleanup_error=str(error))
        try:
            after = source_identity(repo, args.expected_head, args.expected_tree, args.mode)
            save(output/'source-after.json', after)
            assert before == after and pins is not None
            assert pins == {path: sha(path) for path in pins}
            run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--interpreter-probe'], 'client-after')
            receipt['client_after'] = json.loads((output/'client-after.log').read_text())
            assert receipt['client_before'] == receipt['client_after']
            receipt['source_and_runtime_unchanged'] = True
        except BaseException as error:
            receipt.update(outcome='failed_identity', source_and_runtime_unchanged=False, identity_error=str(error))
        for label, expected in [('unit', EXPECTED_UNIT), ('sql', EXPECTED_SQL)]:
            try:
                suites = ET.parse(output/(label+'.xml')).getroot().findall('testsuite')
                counts = {key: sum(int(s.attrib[key]) for s in suites) for key in expected}
                receipt[label+'_tests'] = counts
                if counts != expected:
                    receipt['coverage_error_'+label] = dict(expected=expected, actual=counts)
                    receipt['outcome'] = 'failed_coverage'
            except Exception as error:
                receipt['coverage_error_'+label] = str(error)
                receipt['outcome'] = 'failed_coverage'
        receipt['logs_sha256'] = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
        receipt['finished_utc'] = utc()
        save(output/'receipt.json', receipt)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    if receipt['outcome'] != 'passed':
        raise SystemExit(1)
    print('RESOURCE_VALIDATION_SQL_GATE PASSED '+args.expected_head+' tree='+args.expected_tree)


if __name__ == '__main__':
    if sys.argv[1:] == ['--interpreter-probe']:
        interpreter_probe()
    elif len(sys.argv) == 5 and sys.argv[1] == '--default-statistics-control':
        default_statistics_control(*sys.argv[2:])
    else:
        main()
