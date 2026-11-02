from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-missing-catalog-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-missing-catalog-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-missing-catalog-rust.log').read_text())==['140','15','104','180']
for kind in ['diagnostic','hierarchy']:
 r=json.loads(Path('/tmp/sail-sdp-missing-catalog-'+kind+'-control.json').read_text());log=Path('/tmp/sail-sdp-missing-catalog-'+kind+'-control.log').read_bytes()
 assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['log_sha256'] and b'0 passed; 1 failed;' in log
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-missing-catalog-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence');qualified='/tmp/sail-sdp-missing-catalog-public/receipt.json'
for packet,output in [('missing-catalog-errors','candidate'),('wrapped-catalog-identifier','phases'),('constant-context-lowering','arithmetic'),('identifier-function-provenance','provenance')]:
 subprocess.run([PYTHON,str(p/packet/'run-probe.py'),'/tmp/sail-sdp-missing-catalog-'+output,c['commit'],qualified,'identifier'],check=True)
print('PASS exact-source missing-catalog public and focused probes',flush=True)
