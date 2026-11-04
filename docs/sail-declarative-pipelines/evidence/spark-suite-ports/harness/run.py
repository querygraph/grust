"""Root-executed public regression gate; preparation does not run this script."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/alexy/src/sail-sdp-gate')
DEFAULT_COMMIT = 'ec8e74d57de51149a774cd4f9048d82039704d0c'
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
SPARK_COMMIT = '617618396087429b5627a86ce933bb0f5d6645cb'
VENV = Path('/Users/alexy/src/sail-pipelines-proposal/.venv')
PYTHON = str(VENV / 'bin/python')
SITE = str(VENV / 'lib/python3.12/site-packages')
CLI = ROOT / 'target/debug/sail'
PORT = 50094
REMOTE = f'sc://localhost:{PORT}'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--commit', default=DEFAULT_COMMIT, help='Exact full Sail commit to gate')
parser.add_argument('--output', type=Path, help='Fresh result directory; defaults to a commit-derived path')
arguments = parser.parse_args()
COMMIT = arguments.commit
assert len(COMMIT) == 40 and all(c in '0123456789abcdef' for c in COMMIT), 'use a full lowercase commit hash'
OUT = arguments.output or Path('/tmp/sail-sdp-local-runner-public-' + COMMIT[:12])
BUILD_ENV = {
    'CARGO_INCREMENTAL': '0',
    'CARGO_PROFILE_DEV_DEBUG': '0',
    'CARGO_PROFILE_DEV_INCREMENTAL': 'false',
    'CARGO_TARGET_DIR': str(ROOT / 'target'),
    'PYO3_PYTHON': PYTHON,
    'VIRTUAL_ENV': str(VENV),
    'PYTHONPATH': SITE,
    'PYTHONDONTWRITEBYTECODE': '1',
}
SERVER_ENV = {
    'VIRTUAL_ENV': str(VENV),
    'PYTHONPATH': SITE,
    'PYTHONDONTWRITEBYTECODE': '1',
}
CLIENT_ENV = {
    **SERVER_ENV,
    'PYTHONPATH': str(ROOT / 'python') + os.pathsep + SITE,
    'SPARK_REMOTE': REMOTE,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def owners():
    result = subprocess.run(
        ['/usr/sbin/lsof', '-nP', f'-iTCP:{PORT}', '-sTCP:LISTEN', '-Fp'],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return {int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}


def state(preparation):
    assert git('rev-parse', 'HEAD') == COMMIT
    assert not git('status', '--porcelain', '--untracked-files=all')
    detached = subprocess.run(['git', '-C', str(ROOT), 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
    assert detached.returncode == 1, 'gate checkout must remain detached'
    assert git('rev-parse', 'HEAD', root=SPARK) == SPARK_COMMIT
    assert not git('diff', 'HEAD', '--', 'python/pyspark/pipelines/tests', root=SPARK)
    sources = {path: sha(ROOT / path) for path in preparation['source_sha256']}
    assert sources == preparation['source_sha256'], 'frozen test/helper source changed'
    return {'head': COMMIT, 'tree': git('rev-parse', 'HEAD^{tree}'), 'detached': True,
            'cargo_lock_sha256': sha(ROOT / 'Cargo.lock'), 'sources': sources}


def main():
    # An existing result directory is never overwritten, including failed runs.
    OUT.mkdir(exist_ok=False)
    receipt = {'sail_commit': COMMIT, 'spark_commit': SPARK_COMMIT, 'started_at': now(),
               'outcome': 'running', 'checks': [], 'port': PORT, 'remote': REMOTE,
               'harness_sha256': sha(__file__), 'scope': '300 selected public cases and 67 upstream cases; no withdrawn flow-config assertions'}
    process = None
    preparation = json.loads((HERE / 'preparation.json').read_text())

    def checkpoint():
        write_json(OUT / 'receipt.json', receipt)

    def run(name, command, overrides, timeout=1800, required=True):
        check = {'name': name, 'command': command, 'cwd': str(ROOT),
                 'environment_overrides': overrides, 'started_at': now()}
        receipt['checks'].append(check)
        checkpoint()
        try:
            with (OUT / (name + '.log')).open('x') as log:
                result = subprocess.run(command, cwd=ROOT, env={**os.environ, **overrides},
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=timeout, check=False)
            check['exit_code'] = result.returncode
        finally:
            check['completed_at'] = now()
            check['log_sha256'] = sha(OUT / (name + '.log'))
            checkpoint()
        assert state(preparation) == receipt['before']
        if required:
            assert result.returncode == 0, (name, result.returncode)
            print('PASS ' + name, flush=True)
        return result.returncode

    def interrupted(signum, _frame):
        raise KeyboardInterrupt(f'harness interrupted by signal {signum}')

    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        receipt['selection_preparation_commit'] = preparation['sail_commit']
        receipt['preparation_sha256'] = sha(HERE / 'preparation.json')
        assert sha(HERE / 'selected-nodes.json') == preparation['selected_nodes_sha256']
        for item in preparation['inputs']:
            assert sha(HERE / item['copy']) == item['sha256']
        nodes = json.loads((HERE / 'selected-nodes.json').read_text())
        assert len(nodes) == len(set(nodes)) == 300
        assert not any('test_flow_file_config' in node for node in nodes)
        write_json(OUT / 'selected-nodes.json', nodes)
        receipt['before'] = state(preparation)
        receipt['disk_free_before_build'] = shutil.disk_usage(ROOT).free
        assert receipt['disk_free_before_build'] > 2 * 1024 ** 3
        assert not owners(), f'port {PORT} already has a listener; no process was stopped'
        run('environment', [PYTHON, '-c',
            "import json,sys,pyspark; assert pyspark.__version__=='4.2.1'; print(json.dumps({'python':sys.version,'executable':sys.executable,'pyspark':pyspark.__version__,'pyspark_file':pyspark.__file__}))"], BUILD_ENV)
        # The branch wheel keeps optional format features on (pyproject.toml); the
        # frozen build must match it, or the ports that use those formats refuse.
        features = os.environ.get('SAIL_FROZEN_CLI_FEATURES', '')
        receipt['cli_features'] = features
        run('build', ['cargo', '+1.98.1', 'build', '-p', 'sail-cli', '--locked'] + (['--features', features] if features else []), BUILD_ENV, timeout=7200)
        receipt['cli_path'] = str(CLI)
        receipt['cli_sha256'] = sha(CLI)
        receipt['cli_stat'] = {'size': CLI.stat().st_size, 'mtime_ns': CLI.stat().st_mtime_ns}
        run('cli-version', [str(CLI), '--version'], SERVER_ENV)
        assert not owners(), f'port {PORT} became occupied after build'
        command = [str(CLI), 'spark', 'server', '--port', str(PORT)]
        receipt['server_command'] = command
        receipt['server_environment_overrides'] = SERVER_ENV
        with (OUT / 'server.log').open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **SERVER_ENV},
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            receipt['server_pid'] = process.pid
            checkpoint()
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, 'owned server exited before listening'
                current = owners()
                assert not current or current == {process.pid}, 'another process owns the chosen port'
                if current:
                    break
                assert time.monotonic() < deadline, 'owned server readiness timeout'
                time.sleep(0.25)
            run('server-version', [PYTHON, '-c',
                "import json,pyspark; from pyspark.sql import SparkSession; s=SparkSession.builder.remote('" + REMOTE + "').create();\ntry:\n assert pyspark.__version__==s.version=='4.2.1'; print(json.dumps({'pyspark':pyspark.__version__,'server_spark_version':s.version,'session_class':type(s).__module__+'.'+type(s).__name__}))\nfinally:\n s.stop()"], CLIENT_ENV)
            code = run('pytest', [PYTHON, '-m', 'pytest', '-q', *nodes,
                       '--junitxml=' + str(OUT / 'pytest.xml')], CLIENT_ENV, required=False)
            tree = ET.parse(OUT / 'pytest.xml')
            suites = list(tree.iter('testsuite'))
            assert len(suites) == 1
            receipt['pytest'] = {key: int(suites[0].get(key)) for key in ('tests', 'failures', 'errors', 'skipped')}
            actual = [case.get('classname').replace('.', '/') + '.py::' + case.get('name')
                      for case in tree.iter('testcase')]
            assert Counter(actual) == Counter(nodes), 'public case identities changed'
            assert code == 0 and receipt['pytest'] == dict(tests=300, failures=0, errors=0, skipped=0)
            run('upstream', [PYTHON, 'scripts/spark-pipelines-tests/run.py', '--spark-source', str(SPARK),
                            '--remote', REMOTE, '--report', str(OUT / 'upstream.json')], CLIENT_ENV)
            upstream = json.loads((OUT / 'upstream.json').read_text())
            prior = json.loads((HERE / 'prior-upstream.json').read_text())
            assert upstream['collected'] == prior['collected']
            assert upstream['tests_run'] == 67 and upstream['failures'] == upstream['errors'] == upstream['skipped'] == 0
            assert upstream['server_spark_version'] == upstream['spark_version'] == '4.2.1'
            assert upstream['spark_commit'] == SPARK_COMMIT
            receipt['upstream'] = {key: upstream[key] for key in ('tests_run', 'failures', 'errors', 'skipped', 'server_spark_version')}
            assert sha(CLI) == receipt['cli_sha256'] and owners() == {process.pid}
            receipt['after'] = state(preparation)
        receipt['outcome'] = 'passed'
    except BaseException:
        receipt['outcome'] = 'failed'
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        # Teardown only the exact process created above, never arbitrary listeners.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if process is not None:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        receipt['cleanup_escalation'] = 'terminate owned server'
                        process.terminate()
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            receipt['cleanup_escalation'] = 'kill owned server'
                            process.kill()
                            process.wait(timeout=15)
                receipt['server_exit_code'] = process.returncode
                receipt['remaining_listener_pids'] = sorted(owners())
                if receipt['remaining_listener_pids']:
                    raise RuntimeError('port still has a listener after owned server teardown')
        except BaseException:
            receipt['outcome'] = 'failed'
            receipt['cleanup_error'] = traceback.format_exc()
            raise
        finally:
            receipt['completed_at'] = now()
            receipt['artifact_sha256'] = {path.name: sha(path) for path in sorted(OUT.iterdir())
                                         if path.is_file() and path.name not in ('receipt.json', 'receipt.json.tmp')}
            checkpoint()
    print(f"PASS {COMMIT}: 300 selected public + 67 upstream; owned server stopped", flush=True)


if __name__ == '__main__':
    main()
