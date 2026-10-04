"""Sequentially finish the authorized 289/561 host builds; never launch graphs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / ('orchestration-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
LOGS.mkdir()


def call(script, *args):
    name = script.removesuffix('.py') + '-' + datetime.now(timezone.utc).strftime('%H%M%S%f')
    result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                            text=True, capture_output=True)
    (LOGS / (name + '.stdout')).write_text(result.stdout)
    (LOGS / (name + '.stderr')).write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f'{script} failed ({result.returncode}); {LOGS / name}')
    return json.loads(result.stdout)


def monitor(container, run, label):
    previous = None
    failures = 0
    while True:
        try:
            record = call('observe.py', container, run, label)
        except RuntimeError:
            failures += 1
            # A freshly launched build creates its receipt after read-only seed
            # guards. Retain failed reads; never retry a mutation automatically.
            if failures >= 4:
                raise
            time.sleep(30)
            continue
        failures = 0
        step = (record.get('last_step') or {}).get('name')
        state = (record['outcome'], step, record['state']['Running'])
        if state != previous:
            print(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), container=container,
                                  outcome=state[0], step=step, running=state[2],
                                  free_bytes=record.get('free_bytes'), evidence=record['path'])), flush=True)
            previous = state
        if not record['state']['Running']:
            collected = call('collect.py', container, run, label,
                             'integration289-launch' if label == 'integration289' else 'compact561-host-launch')
            print(json.dumps(dict(collected=collected)), flush=True)
            if record['outcome'] != 'passed' or record['state']['ExitCode'] != 0:
                raise RuntimeError('completed build failed; evidence preserved, no next mutation')
            return collected
        time.sleep(30)


try:
    original = monitor('sail-stream-build289', '/targets/sail-stream-2894a962076d', 'integration289')
    cleanup = call('launch_cleanup.py', '--evidence', original['remote'])
    print(json.dumps(dict(cleanup=cleanup)), flush=True)
    launched = call('launch_host_only.py', '--evidence', original['remote'])
    print(json.dumps(dict(launch=launched)), flush=True)
    time.sleep(30)
    compact = monitor('sail-stream-build561-host', '/targets/sail-compact-host-56194b170155', 'compact561-host')
    (LOGS / 'passed.json').write_text(json.dumps(dict(finished_utc=datetime.now(timezone.utc).isoformat(),
        integration289=original, cleanup=cleanup, compact561_host=compact,
        scope='builds only; no graph workload'), indent=2) + '\n')
    print('SEQUENTIAL_BUILDS PASSED ' + str(LOGS / 'passed.json'), flush=True)
except BaseException as error:
    (LOGS / 'failed.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
        error=repr(error), scope='no automatic mutation retry; inspect retained receipts'), indent=2) + '\n')
    raise
