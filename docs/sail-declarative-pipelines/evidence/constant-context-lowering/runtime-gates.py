from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-constant-context-arithmetic-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-constant-context-arithmetic-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-constant-context-arithmetic-rust.log').read_text())==['101','177']
r=json.loads(Path('/tmp/sail-sdp-constant-lowering-control.json').read_text());log=Path('/tmp/sail-sdp-constant-lowering-control.log').read_bytes();assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['log_sha256'] and b'0 passed; 1 failed;' in log
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-constant-lowering-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/constant-context-lowering');qualified='/tmp/sail-sdp-constant-lowering-public/receipt.json'
subprocess.run([PYTHON,str(p/'run-probe.py'),'/tmp/sail-sdp-constant-lowering-candidate',c['commit'],qualified,'identifier'],check=True)
prior=p.parent/'identifier-function-provenance'
subprocess.run([PYTHON,str(prior/'run-probe.py'),'/tmp/sail-sdp-constant-lowering-provenance',c['commit'],qualified,'identifier'],check=True)
for name,probe in [('validation','reference.py'),('replacement','runtime-replacement-reference.py')]:
 subprocess.run([PYTHON,str(prior/'validation-probes/run-probe.py'),'/tmp/sail-sdp-constant-lowering-'+name,c['commit'],qualified,'identifier',probe],check=True)
for kind in ['dynamic','namespace','expression']:
 subprocess.run([PYTHON,str(prior/'binding-probes/run-probe.py'),'/tmp/sail-sdp-constant-lowering-'+kind,c['commit'],qualified,kind],check=True)
print('PASS exact-source arithmetic and previous public/provenance/binding probes complete',flush=True)
