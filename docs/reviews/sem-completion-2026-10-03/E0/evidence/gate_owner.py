"""Own one native Pecan engine gate and preserve its actual waits and source pin."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003')
VENV = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-int64-build01/venv')
BINARY = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/sail-target/release/sail')
PYHOME = Path('/Users/alexy/.asdf/installs/python/3.12.6')
LOCK = Path('/tmp/morrobay-sem-completion-heavy.lock')


@dataclasses.dataclass
class Receipt:
    started_utc: str
    owner_pid: int
    source_commit: str
    source_tree: str
    server_pid: int | None = None
    test_pid: int | None = None
    test_returncode: int | None = None
    server_returncode: int | None = None
    forced_cleanup: bool = False
    lock_released: bool = False
    source_unchanged: bool = False
    finished_utc: str | None = None
    outcome: str = 'running'
    errors: list[str] = dataclasses.field(default_factory=list)


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def save(path: Path, value: object) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def interrupted(number: int, _frame: object) -> None:
    raise TimeoutError(f'gate interrupted by signal {number}')


def absent(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def owner(repo: Path, output: Path) -> int:
    output.mkdir(exist_ok=False)
    (output / 'staging').mkdir()
    (output / 'tmp').mkdir()
    receipt = Receipt(utc(), os.getpid(), git(repo, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'HEAD^{tree}'))
    record = output / 'receipt.json'
    server: subprocess.Popen[bytes] | None = None
    tests: subprocess.Popen[bytes] | None = None
    locked = False
    try:
        assert not git(repo, 'status', '--porcelain'), 'gate requires clean source'
        LOCK.mkdir()
        locked = True
        (LOCK / 'owner').write_text(str(os.getpid()))
        save(record, dataclasses.asdict(receipt))
        env = {key: value for key, value in os.environ.items() if not key.startswith('SAIL_')}
        env.update({
            'PYTHONHOME': str(PYHOME),
            'PYTHONPATH': str(VENV / 'lib/python3.12/site-packages'),
            'DYLD_LIBRARY_PATH': str(PYHOME / 'lib'),
            'SAIL_EXPERIMENTAL_EXTENSIONS': '1',
            'SAIL_MODE': 'local',
            'SAIL_GRAPH_UTILS_ROOT': (output / 'staging').as_uri(),
            'SAIL_EXECUTION__DEFAULT_PARALLELISM': '16',
            'SAIL_RUNTIME__MEMORY_POOL__TYPE': 'greedy',
            'SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE': str(30 * 1024**3),
            'TOKIO_WORKER_THREADS': '16',
            'RAYON_NUM_THREADS': '16',
            'TMPDIR': str(output / 'tmp'),
            'RUST_LOG': 'warn',
        })
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        with (output / 'server.log').open('xb') as log:
            server = subprocess.Popen([str(BINARY), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        receipt.server_pid = server.pid
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, 'server exited before readiness'
            with socket.socket() as connection:
                connection.settimeout(.2)
                if connection.connect_ex(('127.0.0.1', port)) == 0:
                    break
            assert time.monotonic() < deadline, 'server readiness timed out'
            time.sleep(.05)
        client_env = os.environ.copy()
        client_env.update({'PYTHONPATH': str(repo / 'examples/extensions/graph-algorithms/src'), 'SAIL_GRAPH_TEST_REMOTE': f'sc://127.0.0.1:{port}'})
        with (output / 'pytest.log').open('xb') as log:
            tests = subprocess.Popen([str(VENV / 'bin/python'), '-B', '-m', 'pytest', '-q', 'examples/extensions/graph-algorithms/tests'], cwd=repo, env=client_env, stdout=log, stderr=subprocess.STDOUT)
            receipt.test_pid = tests.pid
            save(record, dataclasses.asdict(receipt))
            receipt.test_returncode = tests.wait(timeout=1200)
        assert receipt.test_returncode == 0, 'Pecan tests failed'
        receipt.outcome = 'passed_native_pecan_engine_gate'
    except BaseException:
        receipt.outcome = 'failed'
        receipt.errors.append(traceback.format_exc())
    finally:
        for process in (tests, server):
            if process is None:
                continue
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                receipt.forced_cleanup = True
                process.kill()
                process.wait(timeout=30)
            if process is tests:
                receipt.test_returncode = process.returncode
            else:
                receipt.server_returncode = process.returncode
                if not absent(process.pid):
                    receipt.errors.append('server process group remains')
        receipt.source_unchanged = git(repo, 'rev-parse', 'HEAD') == receipt.source_commit and git(repo, 'rev-parse', 'HEAD^{tree}') == receipt.source_tree and not git(repo, 'status', '--porcelain')
        if locked:
            assert (LOCK / 'owner').read_text() == str(os.getpid())
            (LOCK / 'owner').unlink()
            LOCK.rmdir()
            receipt.lock_released = True
        if receipt.errors or receipt.forced_cleanup or not receipt.source_unchanged:
            receipt.outcome = 'failed'
        receipt.finished_utc = utc()
        save(record, dataclasses.asdict(receipt))
    return 0 if receipt.outcome == 'passed_native_pecan_engine_gate' else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--supervise', action='store_true')
    args = parser.parse_args()
    if args.supervise:
        with (ROOT / (args.output.name + '-owner.log')).open('xb') as log:
            child = subprocess.Popen([sys.executable, '-I', '-B', __file__, '--repo', str(args.repo), '--output', str(args.output)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            result = child.wait()
        save(ROOT / (args.output.name + '-wait.json'), {'observed_utc': utc(), 'pid': child.pid, 'returncode': result, 'actual_wait_completed': True, 'owner_group_absent': absent(child.pid)})
        raise SystemExit(result)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(number, interrupted)
    signal.alarm(1500)
    raise SystemExit(owner(args.repo, args.output))


if __name__ == '__main__':
    main()
