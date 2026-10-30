"""Optional root-executed foreground supervisor for the freshly verified CLI."""
import os
import signal
import subprocess
import time
import traceback

from common import CLI, LABEL, OUT, PORT, REMOTE, ROOT, SERVER_ENV, candidate, listener_pids, now, sha, snapshot, verify_build, write_json


def main():
    assert not (OUT / 'server.json').exists(), 'archive the prior server attempt first'
    assert not (OUT / 'server.log').exists(), 'refuse to overwrite a server log'
    receipt = {'label': LABEL, 'outcome': 'starting', 'started_at': now(), 'port': PORT,
               'remote': REMOTE, 'environment_overrides': SERVER_ENV,
               'supervisor_pid': os.getpid(), 'command': [str(CLI), 'spark', 'server', '--port', str(PORT)]}
    process = None
    stop = False

    def request_stop(signum, _frame):
        nonlocal stop
        stop = True
        receipt['requested_stop_signal'] = signum

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        expected = candidate()
        receipt['sail_commit'] = expected['commit']
        receipt['before'] = snapshot(expected)
        build = verify_build(expected)
        receipt['cli_sha256'] = build['cli_sha256']
        receipt['build_json_sha256'] = sha(OUT / 'build.json')
        # Root must independently live-check the chosen port. This second check
        # refuses to start alongside an existing listener and never stops it.
        assert not listener_pids(), 'port 50088 already has a listener'
        write_json(OUT / 'server.json', receipt)
        with (OUT / 'server.log').open('x') as log:
            process = subprocess.Popen(receipt['command'], cwd=ROOT, env={**os.environ, **SERVER_ENV},
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            receipt['pid'] = process.pid
            write_json(OUT / 'server.json', receipt)
            deadline = time.monotonic() + 30
            while not stop and time.monotonic() < deadline:
                assert process.poll() is None, 'owned server exited before listening'
                owners = listener_pids()
                assert not owners or owners == {process.pid}, 'another process took port 50088'
                if owners:
                    break
                time.sleep(0.25)
            assert not stop and listener_pids() == {process.pid}, 'server did not become ready'
            assert snapshot(expected) == receipt['before']
            receipt['outcome'] = 'running'
            write_json(OUT / 'server.json', receipt)
            print('READY owned ORC public server pid=' + str(process.pid) + ' port=50088', flush=True)
            while not stop and process.poll() is None:
                time.sleep(0.5)
            if not stop:
                raise RuntimeError('owned server exited unexpectedly: ' + str(process.returncode))
    except BaseException:
        receipt['outcome'] = 'failed'
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    receipt['cleanup_escalation'] = 'owned process terminate'
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        receipt['cleanup_escalation'] = 'owned process kill'
                        process.kill()
                        process.wait(timeout=15)
            receipt['exit_code'] = process.returncode
            check = subprocess.run(['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,command='], text=True, capture_output=True)
            receipt['terminal_pid_check'] = {'exit_code': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr}
            receipt['remaining_listener_pids'] = sorted(listener_pids())
        if receipt['outcome'] == 'running':
            receipt['outcome'] = 'stopped'
        receipt['completed_at'] = now()
        if (OUT / 'server.log').exists():
            receipt['server_log_sha256'] = sha(OUT / 'server.log')
        write_json(OUT / 'server.json', receipt)


if __name__ == '__main__':
    main()
