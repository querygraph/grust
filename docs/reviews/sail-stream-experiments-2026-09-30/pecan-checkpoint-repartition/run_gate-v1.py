#!/usr/bin/env python3
"""Detached Pecan source gate and four tiny installed-runtime SQL controls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
PYTHON = Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python')
BINARY = Path('/Users/alexy/src/sail/.venvs/default/bin/sail')
NATIVE = Path('/Users/alexy/src/sail/python/pysail/_native.abi3.so')


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = json.loads((ROOT / 'source-receipt.json').read_text())
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    package = repo / 'examples/extensions/graph-algorithms'

    def guard():
        assert subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == head
        assert subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
        for name, expected in source['files_sha256'].items():
            assert digest(repo / name) == expected, name

    guard()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('SAIL_') and key not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PYTHONDONTWRITEBYTECODE='1', CARGO_INCREMENTAL='0',
               CARGO_TARGET_DIR='/private/tmp/pecan-checkpoint-repartition-target',
               PYTHONPATH=str(package / 'src'))
    Path(env['CARGO_TARGET_DIR']).mkdir(exist_ok=True)
    receipt = dict(started_utc=utc(), source_head=head, detached=True, source=str(repo),
                   source_receipt_sha256=digest(ROOT / 'source-receipt.json'),
                   runner_sha256=digest(Path(__file__)), commands=[],
                   binary=str(BINARY), binary_sha256=digest(BINARY),
                   installed_native=str(NATIVE), installed_native_sha256=digest(NATIVE),
                   installed_version=subprocess.check_output([str(BINARY), '--version'], text=True).strip(),
                   scope='Frozen Pecan Python source only. Tiny local SQL/Parquet control uses installed Sail identity, not a runtime built from candidate; test-only temporary ownership fixture, not GraphUtils/distributed qualification. No timing claim.')

    def run(command, label, *, environment=env):
        receipt['commands'].append(dict(label=label, argv=command))
        with (output / (label + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=repo, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=180)
        receipt['commands'][-1]['returncode'] = result.returncode
        result.check_returncode()

    server = None
    try:
        run(['git', 'diff', '--check', 'HEAD'], 'diff-check')
        run([str(PYTHON), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(package / 'tests'),
             '-m', 'not integration', '--junitxml=' + str(output / 'unit.xml'),
             '--basetemp=' + str(output / 'unit-temp')], 'unit')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        server_env = dict(env, SAIL_MODE='local', SAIL_EXECUTION__DEFAULT_PARALLELISM='2',
                          TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2', RUST_LOG='warn')
        server_env.pop('PYTHONPATH')
        command = [str(BINARY), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
        receipt['server_command'] = command
        with (output / 'server.log').open('w') as server_log:
            server = subprocess.Popen(command, cwd=output, env=server_env,
                                      stdout=server_log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise RuntimeError('local SQL server exited during startup')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError('local SQL startup timed out')
                    time.sleep(.05)
            run([str(PYTHON), '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                 str(package / 'tests/test_checkpoint_sql.py'),
                 '--junitxml=' + str(output / 'sql.xml'), '--basetemp=' + str(output / 'sql-temp')],
                'local-sql', environment=dict(env, SAIL_GRAPH_TEST_REMOTE='sc://127.0.0.1:' + str(port)))
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='failed', error_type=type(error).__name__, error=str(error))
    finally:
        if server is not None:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(timeout=5)
            receipt['server_reaped'] = server.poll() is not None
        try:
            guard()
            assert digest(BINARY) == receipt['binary_sha256']
            assert digest(NATIVE) == receipt['installed_native_sha256']
            receipt['source_and_runtime_hashes_unchanged'] = True
        except BaseException as error:
            receipt.update(outcome='failed', guard_error=repr(error))
        receipt['finished_utc'] = utc()
        receipt['logs_sha256'] = {file.name: digest(file) for file in output.glob('*.log')}
        try:
            for name in ('unit', 'sql'):
                file = output / (name + '.xml')
                if file.exists():
                    suites = list(ET.parse(file).getroot().iter('testsuite'))
                    receipt[name + '_tests'] = {key: sum(int(s.get(key, 0)) for s in suites)
                                                for key in ('tests', 'failures', 'errors', 'skipped')}
        except Exception as error:
            receipt.update(outcome='failed', receipt_parse_error=repr(error))
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
