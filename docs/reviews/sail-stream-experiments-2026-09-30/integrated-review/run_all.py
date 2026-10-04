from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, re, sys, shutil, os

root = Path('/private/tmp/sail-stream-review-integrated-gate')
evidence = Path('/tmp/stream-review-integrated-evidence')
label = sys.argv[1]
sha = sys.argv[2] if len(sys.argv) == 3 else None
out = evidence / label
out.mkdir(exist_ok=False)
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'expected_sha': sha,
          'candidate_not_commit': sha is None, 'free_bytes_before': shutil.disk_usage(root).free,
          'host': os.uname().nodename, 'scope': 'Combined local host, Pecan nonintegration, Argentea core, and full native adapter gates; no release or remote execution verdict.',
          'steps': []}
args = [sha] if sha else []
commands = [
    ('host', ['python3', str(evidence / 'run_host.py'), str(out / 'host'), *args]),
    ('native', ['python3', str(evidence / 'run_native.py'), str(out / 'native'), *args]),
    ('core', ['python3', str(root / 'examples/extensions/argentea/probe.py'), '--output', str(out / 'core'), '--target-dir', '/private/tmp/sail-stream-review-integrated-core-target', *([] if sha else ['--allow-working-tree'])]),
]
jobs = []
for name, command in commands:
    log = (out / f'{name}-runner.log').open('x')
    process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
    jobs.append((name, command, process, log))
for name, command, process, log in jobs:
    status = process.wait()
    log.close()
    record['steps'].append({'name': name, 'command': command, 'exit_code': status})
    print(name, status, flush=True)
    print('\n'.join((out / f'{name}-runner.log').read_text().splitlines()[-4:]), flush=True)

def count(path):
    return sum(int(n) for n in re.findall(r'^test result: ok\. (\d+) passed;', path.read_text(), re.M)) if path.exists() else 0

counts = {'host': count(out / 'host/tests.log'), 'native': count(out / 'native/release.stdout'), 'core': count(out / 'core/release.log')}
pecan = (out / 'host/pecan-nonintegration.log').read_text() if (out / 'host/pecan-nonintegration.log').exists() else ''
counts['pecan'] = int(re.search(r'\b(\d+) passed\b', pecan).group(1)) if re.search(r'\b(\d+) passed\b', pecan) else 0
record['counts'] = counts
record['expected_counts'] = {'host': 490, 'native': 49, 'core': 103, 'pecan': 46}
record['finished_utc'] = datetime.now(timezone.utc).isoformat()
record['free_bytes_after'] = shutil.disk_usage(root).free
record['outcome'] = 'passed' if all(s['exit_code'] == 0 for s in record['steps']) and counts == record['expected_counts'] else 'failed'
(out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print('STREAM_REVIEW_INTEGRATED', record['outcome'].upper(), sha or 'PRECOMMIT_CANDIDATE', counts)
raise SystemExit(0 if record['outcome'] == 'passed' else 1)
