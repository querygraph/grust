"""Detached Python benchmark gate, including actual local Sail SQL validators."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

PYTHON = '/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'
BINARY = Path('/Users/alexy/src/sail/.venvs/default/bin/sail')
NATIVE = Path('/Users/alexy/src/sail/python/pysail/_native.abi3.so')


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(exist_ok=False)
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    assert subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
    assert not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip()
    free = shutil.disk_usage(repo).free
    assert free >= 1 << 30
    files = [repo/'examples/extensions/benchmarks'/name for name in
             ['graph_cell.py', 'ranking_validation.py', 'test_pagerank_metadata.py']]
    pins = {str(path): sha(path) for path in [*files, BINARY, NATIVE, Path(__file__)]}
    assert pins[str(BINARY)] == '27c01027afe78f6403d8c02c34199e30ef9103d11adb24403a6575b4bca40a09'
    assert pins[str(NATIVE)] == 'b99f1717cf49706f17eefd44d78c3751e6fd2b46a34ce3fd2cc360087b7f9685'
    private = Path(tempfile.mkdtemp(prefix='pagerank-metadata-gate-'))
    bench = repo/'examples/extensions/benchmarks'
    env = {k: v for k, v in os.environ.items() if not k.startswith('SAIL_') and k not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PYTHONDONTWRITEBYTECODE='1', CARGO_INCREMENTAL='0', CARGO_TARGET_DIR=str(private/'target'),
               PYTHONPATH=os.pathsep.join(map(str, [bench, repo/'examples/extensions/nutmeg/python',
                                                    repo/'examples/extensions/graph-algorithms/src'])))
    receipt = dict(started_utc=utc(), source_commit=head, detached=True, free_disk_before=free,
                   source_pins=pins, private_fixtures=str(private), commands=[],
                   driver_python=dict(executable=sys.executable, version=sys.version),
                   scope='Python benchmark suite plus actual local SQL/Parquet on pinned installed Sail 0.7.0. No candidate runtime build, distributed or performance verdict.')

    def run(command, label, environment=env):
        record = dict(label=label, command=command)
        receipt['commands'].append(record)
        with (output/(label+'.log')).open('w') as log:
            p = subprocess.run(command, cwd=repo, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        record['returncode'] = p.returncode
        p.check_returncode()

    server = None
    try:
        run(['git', 'diff', '--check', 'HEAD'], 'diff-check')
        run([PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(bench),
             '--junitxml='+str(output/'unit.xml'), '--basetemp='+str(private/'unit')], 'unit')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        server_env = dict(env, SAIL_MODE='local', SAIL_EXECUTION__DEFAULT_PARALLELISM='2',
                          TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2', RUST_LOG='warn')
        server_env.pop('PYTHONPATH')
        command = [str(BINARY), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
        receipt['server_command'] = command
        with (output/'server.log').open('w') as log:
            server = subprocess.Popen(command, cwd=private, env=server_env, stdout=log, stderr=subprocess.STDOUT)
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
        run([PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(bench/'test_pagerank_metadata.py'),
             str(bench/'test_wcc_certificate.py'), '--junitxml='+str(output/'sql.xml'),
             '--basetemp='+str(private/'sql')], 'sql', dict(env, SAIL_GRAPH_TEST_REMOTE=f'sc://127.0.0.1:{port}'))
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='failed', error_type=type(error).__name__, error=str(error))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
            receipt['server_reaped'] = True
        unchanged = pins == {path: sha(Path(path)) for path in pins}
        unchanged = unchanged and head == subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        unchanged = unchanged and not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip()
        receipt['source_and_runtime_unchanged'] = unchanged
        if not unchanged:
            receipt['outcome'] = 'failed_identity'
        for label in ('unit', 'sql'):
            path = output/(label+'.xml')
            if path.exists():
                try:
                    suites = ET.parse(path).getroot().findall('testsuite')
                    receipt[label+'_tests'] = {k: sum(int(s.attrib[k]) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
                except Exception as error:
                    receipt.update(outcome='failed_receipt', receipt_error=repr(error))
        if receipt['outcome'] == 'passed' and receipt.get('sql_tests') != dict(tests=58, failures=0, errors=0, skipped=0):
            receipt['outcome'] = 'failed_sql_coverage'
        receipt['logs_sha256'] = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
        receipt['finished_utc'] = utc()
        (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if receipt['outcome'] != 'passed':
        raise SystemExit(1)
    print('PAGERANK_METADATA_GATE PASSED '+head)


if __name__ == '__main__':
    main()
