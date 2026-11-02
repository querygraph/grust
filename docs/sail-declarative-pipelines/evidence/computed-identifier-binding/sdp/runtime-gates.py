from pathlib import Path
import hashlib,json,os,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-sdp-computed-binding-v2-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-sdp-computed-binding-v2-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
subprocess.run([PYTHON,'/tmp/sail-sdp-computed-target-control.py'],check=True)
r=json.loads(Path('/tmp/sail-sdp-sdp-computed-target-control.json').read_text());assert r['base']==c['commit'] and r['exit_code']==101
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-computed-binding-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/computed-identifier-binding')
for kind in ['dynamic','namespace','expression']:
 subprocess.run([PYTHON,str(p/'run-probe.py'),'/tmp/sail-sdp-computed-binding-'+kind,c['commit'],'/tmp/sail-sdp-computed-binding-public/receipt.json',kind],check=True)
print('PASS public and feature probes completed against exact computed binding candidate',flush=True)
