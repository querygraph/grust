from pathlib import Path
import hashlib,json,os,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-identifier-constants-ready-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-identifier-constants-ready-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-identifier-constants-ready-rust.log').read_text())==['97','177']
for label in ['phase','foldability','parameter']:
 r=json.loads(Path('/tmp/sail-sdp-identifier-constant-'+label+'-control.json').read_text());log=Path('/tmp/sail-sdp-identifier-constant-'+label+'-control.log').read_bytes()
 assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['log_sha256'] and b'2 passed; 1 failed;' in log
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-identifier-constant-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/identifier-constant-validation')
subprocess.run([PYTHON,str(p/'run-probe.py'),'/tmp/sail-sdp-identifier-constant-candidate',c['commit'],'/tmp/sail-sdp-identifier-constant-public/receipt.json','identifier'],check=True)
for kind in ['dynamic','namespace','expression']:
 subprocess.run([PYTHON,str(p/'binding-probes/run-probe.py'),'/tmp/sail-sdp-identifier-constant-'+kind,c['commit'],'/tmp/sail-sdp-identifier-constant-public/receipt.json',kind],check=True)
print('PASS exact fresh public / parameter / identifier and previous binding probes completed',flush=True)
