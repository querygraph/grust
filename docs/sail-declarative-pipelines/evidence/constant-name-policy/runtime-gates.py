from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-constant-policy-candidate.json').read_text())
r=json.loads(Path('/tmp/sail-sdp-constant-policy-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:
 assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-constant-policy-rust.log').read_text())==['101','177']
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-constant-policy-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence')
qualified='/tmp/sail-sdp-constant-policy-public/receipt.json'
subprocess.run([PYTHON,str(p/'constant-context-lowering/run-probe.py'),'/tmp/sail-sdp-constant-policy-arithmetic',c['commit'],qualified,'identifier'],check=True)
subprocess.run([PYTHON,str(p/'identifier-function-provenance/run-probe.py'),'/tmp/sail-sdp-constant-policy-provenance',c['commit'],qualified,'identifier'],check=True)
print('PASS exact-source constant policy public and focused probes',flush=True)
