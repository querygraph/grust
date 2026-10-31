"""Run the identical probe against the previously qualified, immutable Sail CLI."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import subprocess
import time
import sys

ROOT = Path('/Users/alexy/src/sail-sdp-gate')
PYTHON = '/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
VENV = '/Users/alexy/src/sail-pipelines-proposal/.venv'
HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1])
COMMIT = sys.argv[2]
KIND = sys.argv[4]
assert KIND == 'dynamic'
PROBE = HERE/'reference.py'
CLI = ROOT / 'target/debug/sail'
QUALIFIED = Path(sys.argv[3])
assert json.loads(QUALIFIED.read_text())['sail_commit'] == COMMIT
OUT.mkdir(exist_ok=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state():
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == COMMIT
    assert not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()
    assert subprocess.run(['git', '-C', str(ROOT), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
    cli = digest(CLI)
    assert cli == json.loads(QUALIFIED.read_text())['cli_sha256']
    return {'sail_commit': head, 'cli_sha256': cli, 'probe_sha256': digest(PROBE)}


def owners():
    p = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:50094', '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
    assert p.returncode in (0, 1)
    return [int(line[1:]) for line in p.stdout.splitlines() if line.startswith('p')]


report = {'started_at': datetime.now(timezone.utc).isoformat(), 'before': state(), 'scope': KIND+' public SQL probes against fresh exact-source CLI; all differences recorded'}
server = None
try:
    assert owners() == []
    env = {**os.environ, 'VIRTUAL_ENV': VENV, 'PYTHONPATH': VENV+'/lib/python3.12/site-packages', 'PYTHONDONTWRITEBYTECODE': '1'}
    with (OUT/'server.log').open('x') as log:
        server = subprocess.Popen([str(CLI), 'spark', 'server', '--port', '50094'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        report['server_pid'] = server.pid
        deadline = time.monotonic()+30
        while owners() != [server.pid]:
            assert server.poll() is None and time.monotonic()<deadline
            time.sleep(.1)
        with (OUT/'probe.log').open('x') as probe_log:
            result = subprocess.run([PYTHON, str(PROBE), str(OUT/'probe'), 'sail'], cwd=ROOT, env=env, stdout=probe_log, stderr=subprocess.STDOUT, timeout=180)
        report['probe_exit_code'] = result.returncode
        assert result.returncode == 0
        report['after'] = state()
        assert report['before'] == report['after']
finally:
    if server is not None:
        if server.poll() is None:
            server.send_signal(signal.SIGINT)
        report['server_exit_code'] = server.wait(timeout=30)
    report['remaining_listener_pids'] = owners()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    report['files'] = [{'path': str(p.relative_to(OUT)), 'sha256': digest(p)} for p in OUT.rglob('*') if p.is_file()]
    (OUT/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
assert report['server_exit_code'] == 0 and report['remaining_listener_pids'] == []
print('Sail '+KIND+' candidate recorded; server exit0/no listeners', flush=True)
