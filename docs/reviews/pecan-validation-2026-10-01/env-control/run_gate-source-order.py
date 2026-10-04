#!/usr/bin/env python3
"""Detached Pecan Python/SQL gate; no builds, installation or remote hosts."""
import argparse
from collections import Counter
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET

import pytest

HELPER = Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/sql_gate.py')
HELPER_SHA = 'eaebc96443f9edc621adb1a937d7042ef3b8decaae757693f03872d7ad8fbb96'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
BASE = runpy.run_path(str(HELPER))
PYTHON, PYHOME, PYLIB = (BASE[name] for name in ('PYTHON', 'PYHOME', 'PYLIB'))
sha, save, git, source_identity = (BASE[name] for name in ('sha', 'save', 'git', 'source_identity'))
BINARY = Path('/private/tmp/sail-resource-validation-union-target/host/debug/sail')
BINARY_SHA = '4b976fd7a809cb059c72a2119293f490105ff0ed375feaf0ccb5f3e5dad88662'
HOST_COMMIT = 'a3462345a6764096024c055dc4d105a3c634e5a4'
SUITES = ('examples/extensions/graph-algorithms/tests', 'examples/extensions/argentea/python',
          'examples/extensions/benchmarks')


def module_origins(repo):
    modules = {}
    for name, directory in (('pyspark_pecan', 'graph-algorithms/src'), ('sail_nutmeg', 'nutmeg/python')):
        path = Path(importlib.import_module(name).__file__).resolve()
        assert path == (repo/'examples/extensions'/directory/name/'__init__.py').resolve(), (name, path)
        modules[name] = dict(path=str(path), sha256=sha(path))
    print(json.dumps(modules, sort_keys=True))


def offline_skip(item):
    if 'spark' in item.fixturenames:
        return 'set SAIL_GRAPH_TEST_REMOTE'
    module, name = item.path.name, item.originalname
    if module == 'test_graph500_fixture.py' and 'generator' in item.fixturenames:
        return 'set GRAPH500_SOURCE'
    if module == 'test_graph500_matrix.py' and name == 'test_preparation_command_generates_real_graph500_fixture':
        return 'set GRAPH500_MATRIX_GENERATOR'
    if module == 'test_traversal_controls.py':
        if name in ('test_real_controls_match_every_reference_distance', 'test_real_controls_preserve_explicit_isolated_source'):
            return 'set control binary environment variables'
        if name in ('test_parallel_dense_multigraph_tuning_keeps_positive_threshold', 'test_control_mismatch_retains_full_output_and_receipt'):
            return 'set PARALLEL_CONTROL_BINARY'
    return None


def collect_inventory(root):
    class Inventory:
        items = []

        def pytest_collection_modifyitems(self, items):
            for item in items:
                parts = item.nodeid.split('::')
                self.items.append(dict(nodeid=item.nodeid, module=str(item.path.relative_to(root)),
                    classname='.'.join([parts[0][:-3].replace('/', '.'), *parts[1:-1]]),
                    name=item.name, spark='spark' in item.fixturenames, offline_skip=offline_skip(item)))
    inventory = Inventory()
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        result = pytest.main(['--collect-only', '-q', '-p', 'no:cacheprovider', '--rootdir='+str(root),
                             *[str(root/path) for path in SUITES]], plugins=[inventory])
    if result:
        raise RuntimeError(captured.getvalue())
    print(json.dumps(dict(items=inventory.items, collection_output=captured.getvalue())))


def group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        rows = subprocess.check_output(['ps', '-axo', 'pid=,pgid='], text=True, timeout=5)
        return any(line.split()[1] == str(pid) for line in rows.splitlines() if len(line.split()) == 2)


def stop(process):
    process.poll()
    if group_exists(process.pid):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        until = time.monotonic()+10
        while group_exists(process.pid) and time.monotonic() < until:
            process.poll()
            time.sleep(.05)
        if group_exists(process.pid):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)
    until = time.monotonic()+5
    while group_exists(process.pid) and time.monotonic() < until:
        time.sleep(.05)
    assert not group_exists(process.pid), 'owned process group remains'


def xml_result(path, expected, offline):
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    keys = [(row.attrib['classname'], row.attrib['name']) for row in cases]
    wanted = [(row['classname'], row['name']) for row in expected]
    assert Counter(keys) == Counter(wanted), 'JUnit case inventory differs from collection'
    assert len(set(keys)) == len(keys), 'duplicate JUnit case'
    skipped = {(row.attrib['classname'], row.attrib['name']): row.find('skipped').attrib
               for row in cases if row.find('skipped') is not None}
    permitted = {(row['classname'], row['name']): row['offline_skip'] for row in expected if offline and row['offline_skip']}
    assert set(skipped) == set(permitted), 'unexpected skip, or missing declared offline skip'
    if offline:
        assert all(permitted[key] in value.get('message', '') for key, value in skipped.items())
    counts = dict(tests=len(cases), skipped=len(skipped),
                  failures=sum(row.find('failure') is not None for row in cases),
                  errors=sum(row.find('error') is not None for row in cases))
    assert counts['failures'] == counts['errors'] == 0, counts
    counts['passed'] = counts['tests']-counts['skipped']
    counts['skipped_cases'] = [dict(classname=k[0], name=k[1], **v) for k, v in skipped.items()]
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-tree', required=True)
    parser.add_argument('--expected-tests', type=int, required=True)
    parser.add_argument('--action-probe', type=Path, required=True)
    parser.add_argument('--action-probe-sha256', required=True)
    parser.add_argument('--mode', choices=['candidate', 'exact'], required=True)
    args = parser.parse_args()
    args.action_probe = args.action_probe.resolve(strict=True)
    repo, output = args.repo.resolve(), args.output.resolve()
    assert repo != output and repo not in output.parents
    output.mkdir(parents=False, exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='pecan-validation-gate-'))
    env = BASE['client_environment'](repo/'examples/extensions/benchmarks', repo)
    env['PYTHONPATH'] = os.pathsep.join(map(str, [repo/'examples/extensions/benchmarks',
        repo/'examples/extensions/nutmeg/python', repo/'examples/extensions/graph-algorithms/src', BASE['CLIENT']]))
    env['CARGO_TARGET_DIR'] = str(private/'unused-target')
    for key in ('SAIL_GRAPH_TEST_REMOTE', 'GRAPH500_SOURCE', 'GRAPH500_MATRIX_GENERATOR', 'GAP_CONTROL_BINARY', 'PARALLEL_CONTROL_BINARY'):
        env.pop(key, None)
    env['PYTEST_ADDOPTS'] = ''
    receipt = dict(started_utc=BASE['utc'](), outcome='FAILED', mode=args.mode,
        head=args.expected_head, tree=args.expected_tree, private_fixtures=str(private), commands=[], modules=[],
        host=dict(hostname=platform.node(), machine=platform.machine(), platform=platform.platform()),
        runtime=dict(binary=str(BINARY), sha256=BINARY_SHA, built_commit=HOST_COMMIT, profile='dev debug=0'),
        scope='Full Pecan/Argentea/benchmark Python suites, all Pecan modules and Spark-fixture benchmark modules live; local SQL only. Explicit generator/control-binary skips; no builds, worker/Flight/native qualification or performance claim.')
    before = pins = None
    server = active = None

    def guard():
        assert source_identity(repo, args.expected_head, args.expected_tree, args.mode) == before

    def run(command, label, environment=env):
        nonlocal active
        guard()
        record = dict(label=label, command=list(map(str, command)), started_utc=BASE['utc']())
        receipt['commands'].append(record)
        with (output/(label+'.log')).open('x') as log:
            active = subprocess.Popen(command, cwd=repo, env=environment, stdout=log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
            try:
                record['returncode'] = active.wait(timeout=600)
            finally:
                stop(active)
                record.update(group_absent=True, finished_utc=BASE['utc']())
                active = None
                guard()
        assert record['returncode'] == 0, label+' failed; original log retained'

    def interrupted(signum, _frame):
        raise InterruptedError('signal '+str(signum))

    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        assert sys.version_info[:3] == (3, 12, 8) and Path(sys.executable).resolve() == PYTHON.resolve()
        assert platform.machine() == 'arm64' and shutil.disk_usage(repo).free >= 2 << 30
        before = source_identity(repo, args.expected_head, args.expected_tree, args.mode)
        save(output/'source-before.json', before)
        assert not git(repo, 'diff', HOST_COMMIT, '--', 'crates', 'Cargo.toml', 'Cargo.lock', '.cargo'), 'host source changed'
        assert sha(BINARY) == BINARY_SHA
        assert sha(args.action_probe) == args.action_probe_sha256
        pins = {str(p): sha(p) for p in (BINARY, PYTHON.resolve(), PYLIB, Path(__file__).resolve(), HELPER, args.action_probe)}
        package = repo/'examples/extensions/graph-algorithms/src/pyspark_pecan'
        assert all(not p.is_symlink() for p in package.rglob('*.py'))
        rows = [dict(path=str(p.relative_to(package)), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(package.rglob('*.py'))]
        package_sha = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        receipt['pins'] = pins
        run([str(PYTHON), '-B', str(HELPER), '--interpreter-probe'], 'client-before')
        receipt['client_before'] = json.loads((output/'client-before.log').read_text())
        run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--module-origin-probe', str(repo)], 'modules-before')
        receipt['modules_before'] = json.loads((output/'modules-before.log').read_text())
        run(['git', '-C', str(repo), 'diff', '--check', 'HEAD'], 'diff-check')
        run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--collect', str(repo)], 'collection')
        inventory = json.loads((output/'collection.log').read_text())
        items = inventory['items']
        assert len(items) == args.expected_tests > 0
        save(output/'inventory.json', inventory)
        command = [str(PYTHON), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--rootdir='+str(repo)]
        run(command+[str(repo/path) for path in SUITES]+['--junitxml='+str(output/'offline.xml'),
                     '--basetemp='+str(private/'offline')], 'offline')
        receipt['offline'] = xml_result(output/'offline.xml', items, True)
        live = {row['module'] for row in items if row['spark'] or row['module'].startswith(SUITES[0]+'/')}
        for number, module in enumerate(sorted(live)):
            label = f'sql-{number:02d}-'+Path(module).stem
            directory = private/label
            directory.mkdir()
            staging = directory/'staging'
            staging.mkdir()
            selected = dict(SAIL_MODE='local', SAIL_EXPERIMENTAL_EXTENSIONS='1',
                SAIL_EXPERIMENTAL_PROCESS_WORKERS='0', SAIL_EXECUTION__DEFAULT_PARALLELISM='2',
                SAIL_EXECUTION__COLLECT_STATISTICS='true', SAIL_RUNTIME__MEMORY_POOL__TYPE='greedy',
                SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(2 << 30),
                SAIL_GRAPH_UTILS_ROOT=staging.as_uri(), TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2', RUST_LOG='warn')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            record = dict(module=module, selected_server_environment=selected)
            receipt['modules'].append(record)
            launch = [str(BINARY), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
            with (output/(label+'-server.log')).open('x') as log:
                server = subprocess.Popen(launch, cwd=directory, env=dict(env, **selected),
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record.update(server_command=launch, server_pid_and_pgid=server.pid)
            try:
                until = time.monotonic()+60
                while True:
                    assert server.poll() is None, 'server exited at startup'
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2):
                            break
                    except OSError:
                        if time.monotonic() > until:
                            raise TimeoutError('server startup exceeded 60s')
                        time.sleep(.05)
                sql_env = dict(env, SAIL_GRAPH_TEST_REMOTE=f'sc://127.0.0.1:{port}')
                run(command+[str(repo/module), '--junitxml='+str(output/(label+'.xml')),
                    '--basetemp='+str(directory/'pytest')], label, sql_env)
                record['counts'] = xml_result(output/(label+'.xml'), [r for r in items if r['module'] == module], False)
                if number == len(live)-1:
                    run([str(PYTHON), '-B', str(args.action_probe), '--repo', str(repo),
                         '--source-commit', args.expected_head, '--package-sha256', package_sha,
                         '--remote', sql_env['SAIL_GRAPH_TEST_REMOTE'], '--runtime-label', json.dumps(receipt['runtime']),
                         '--output', str(output/'action-probe')], 'action-probe', sql_env)
                    receipt['action_probe'] = json.loads((output/'action-probe/receipt.json').read_text())
                    assert receipt['action_probe']['outcome'] == 'PASS_EXACT_ORACLE_AND_ACTION_REDUCTION'
                assert server.poll() is None, 'server exited unexpectedly'
            finally:
                stop(server)
                record.update(server_reaped=True, server_group_absent=True, server_returncode=server.returncode)
                server = None
        receipt['sql'] = {key: sum(r['counts'][key] for r in receipt['modules'])
                          for key in ('tests', 'passed', 'skipped', 'failures', 'errors')}
        assert receipt['sql']['passed'] == sum(row['module'] in live for row in items)
        receipt['outcome'] = 'PASS'
    except BaseException as error:
        receipt.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        for signum in handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            for process in (active, server):
                if process is not None:
                    stop(process)
            after = source_identity(repo, args.expected_head, args.expected_tree, args.mode)
            save(output/'source-after.json', after)
            assert before == after and pins == {path: sha(path) for path in pins}
            run([str(PYTHON), '-B', str(HELPER), '--interpreter-probe'], 'client-after')
            receipt['client_after'] = json.loads((output/'client-after.log').read_text())
            assert receipt['client_before'] == receipt['client_after']
            run([str(PYTHON), '-B', str(Path(__file__).resolve()), '--module-origin-probe', str(repo)], 'modules-after')
            assert receipt['modules_before'] == json.loads((output/'modules-after.log').read_text())
            receipt['source_runtime_client_unchanged'] = True
        except BaseException as error:
            receipt.update(outcome='FAILED', final_guard_or_cleanup_error=repr(error))
        receipt['raw_xml_counts'] = {}
        for path in output.glob('*.xml'):
            try:
                cases = ET.parse(path).getroot().findall('.//testcase')
                receipt['raw_xml_counts'][path.name] = dict(tests=len(cases), **{
                    kind: sum(row.find(kind) is not None for row in cases)
                    for kind in ('failure', 'error', 'skipped')})
            except Exception as error:
                receipt.update(outcome='FAILED', xml_parse_error=repr(error))
        receipt['files_sha256'] = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
        receipt['finished_utc'] = BASE['utc']()
        save(output/'receipt.json', receipt)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    print('PECAN_VALIDATION_GATE', receipt['outcome'], args.expected_head)
    return 0 if receipt['outcome'] == 'PASS' else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--collect':
        collect_inventory(Path(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == '--module-origin-probe':
        module_origins(Path(sys.argv[2]))
    else:
        raise SystemExit(main())
