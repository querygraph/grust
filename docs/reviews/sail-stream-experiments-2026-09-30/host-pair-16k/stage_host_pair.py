"""Stage a pinned plan without replacing files or invoking Docker/workloads.

Dry by default. This writes only new uniquely named scripts/configs/plan to the
already prepared remote host directory. Existing support/harness files are read
and hash-checked; no dataset, source, target, venv or previous trial is changed.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys

from run_host_pair import sha

REMOTE_CODE = r'''
import base64,hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
payload=json.load(sys.stdin)
root=Path(payload['remote_root'])
assert root.is_dir() and not root.is_symlink()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name,expected in payload['support'].items():
 p=root/name
 assert p.is_file() and not p.is_symlink() and sha(p)==expected, name
assert not (root/payload['namespace']).exists(), 'study output already exists'
for name,item in payload['files'].items():
 assert Path(name).name==name
 p=root/name
 assert not p.exists() and not p.is_symlink(), 'staged filename already exists: '+name
 data=base64.b64decode(item['base64'],validate=True)
 assert hashlib.sha256(data).hexdigest()==item['sha256']
for name,item in payload['files'].items():
 p=root/name
 with p.open('xb') as stream: stream.write(base64.b64decode(item['base64'],validate=True))
 assert sha(p)==item['sha256']
# This is the paired runner's default dry path: validates config hashes, no Docker.
result=subprocess.run([sys.executable,'-B',str(root/payload['runner']),str(root/payload['plan'])],
 capture_output=True,text=True,timeout=60)
receipt={'utc':datetime.now(timezone.utc).isoformat(),'scope':'staging and pure dry plan only; no Docker or workload',
 'namespace':payload['namespace'],'files_sha256':{n:i['sha256'] for n,i in payload['files'].items()},
 'support_sha256':payload['support'],'dry_returncode':result.returncode,
 'dry_stdout':result.stdout,'dry_stderr':result.stderr}
with (root/(payload['namespace']+'-staging.json')).open('x') as stream:
 json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt))
raise SystemExit(result.returncode)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--expected-plan-sha256', required=True)
    args = parser.parse_args()
    assert sha(args.plan) == args.expected_plan_sha256
    root = args.plan.resolve().parent
    plan = json.loads(args.plan.read_text())
    assert sha(root / 'run_host_pair.py') == plan['scripts']['run_host_pair.py']
    runner = plan['namespace'] + '-runner.py'
    files = {runner: root / 'run_host_pair.py', args.plan.name: args.plan}
    files.update({entry['configuration']: root / entry['configuration'] for entry in plan['runs']})
    for entry in plan['runs']:
        assert sha(root / entry['configuration']) == entry['configuration_sha256']
    payload = dict(remote_root=plan['remote_root'], namespace=plan['namespace'],
        runner=runner, plan=args.plan.name,
        support={name: value for name, value in plan['scripts'].items() if name != 'run_host_pair.py'},
        files={name: dict(sha256=sha(path), base64=base64.b64encode(path.read_bytes()).decode())
               for name, path in files.items()})
    payload['support'].update({'harness/' + name: value for name, value in plan['harness_files_sha256'].items()})
    if not args.stage:
        print(json.dumps(dict(scope='dry staging plan; no remote operations',
            files_sha256={name: item['sha256'] for name, item in payload['files'].items()}), indent=2))
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(), plan_sha256=sha(args.plan),
                   staging_script_sha256=sha(__file__), scope='new files only, no workload launch')
    command = ['ssh', 'morrobay', 'python3 -c ' + shlex.quote(REMOTE_CODE)]
    path = root / ('staging-' + stamp + '.json')
    try:
        result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, timeout=120)
        receipt.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        result.check_returncode()
    except BaseException as error:
        receipt.update(error=repr(error),
            remote_state='unknown if SSH interrupted; preserve any partial files; no automatic retry or deletion')
        raise
    finally:
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with path.open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
        print(json.dumps(dict(receipt=str(path), returncode=receipt.get('returncode'), error=receipt.get('error'))))



if __name__ == '__main__':
    main()
