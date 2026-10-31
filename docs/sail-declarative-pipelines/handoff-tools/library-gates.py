from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

label, *packages = sys.argv[1:]
root = Path('/Users/alexy/src/sail-sdp-gate')
candidate = json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
def git(*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD') == candidate['commit']
assert not git('status','--porcelain')
assert subprocess.run(['git','-C',str(root),'symbolic-ref','-q','HEAD'],capture_output=True).returncode == 1
assert shutil.disk_usage(root).free > 2*1024**3, 'Free at least 2GiB before compilation'
env = {**os.environ, 'CARGO_PROFILE_DEV_DEBUG':'0', 'CARGO_PROFILE_DEV_INCREMENTAL':'false',
       'CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python',
       'PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages',
       'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv'}
flags = [item for package in packages for item in ['-p',package]]
commands = [
    ('fmt',['cargo','+nightly','fmt',*flags,'--','--check']),
    ('clippy',['cargo','+1.98.1','clippy',*flags,'--all-targets','--all-features','--locked','--','-D','warnings']),
    ('rust',['cargo','+1.98.1','test',*flags,'--lib','--locked']),
]
receipt = {'sail_commit': candidate['commit'], 'base':candidate['base'], 'packages':packages,
           'started_at':datetime.now(timezone.utc).isoformat(), 'checks':[], 'scope':'Rust library gates only; no public CLI or SDP runtime verdict',
           'environment_overrides':{k:env[k] for k in ['CARGO_PROFILE_DEV_DEBUG','CARGO_PROFILE_DEV_INCREMENTAL','CARGO_INCREMENTAL','PYO3_PYTHON','PYTHONPATH','VIRTUAL_ENV']}}
for name,command in commands:
    assert git('rev-parse','HEAD') == candidate['commit']
    log = Path('/tmp/sail-sdp-'+label+'-'+name+'.log')
    with log.open('w') as output:
        result = subprocess.run(command,cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT)
    check = {'name':name,'command':command,'exit_code':result.returncode,'log':str(log),
             'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    receipt['checks'].append(check)
    receipt['recorded_at'] = datetime.now(timezone.utc).isoformat()
    Path('/tmp/sail-sdp-'+label+'-gate.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if result.returncode:
        print(log.read_text()[-15000:],flush=True)
        raise SystemExit(result.returncode)
    print('PASS '+label+' '+name,flush=True)
assert git('rev-parse','HEAD') == candidate['commit']
assert not git('status','--porcelain')
receipt['outcome'] = 'passed'
receipt['recorded_at'] = datetime.now(timezone.utc).isoformat()
Path('/tmp/sail-sdp-'+label+'-gate.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS detached library gate '+candidate['commit'],flush=True)
