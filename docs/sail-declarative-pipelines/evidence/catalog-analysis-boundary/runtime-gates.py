from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-catalog-analysis-boundary-candidate.json').read_text())
r=json.loads(Path('/tmp/sail-sdp-catalog-analysis-boundary-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-catalog-analysis-boundary-rust.log').read_text())==['178']
r=json.loads(Path('/tmp/sail-sdp-catalog-analysis-boundary-control.json').read_text());assert r['base']==c['commit'] and r['exit_code']==101
assert hashlib.sha256(Path('/tmp/sail-sdp-catalog-analysis-boundary-control.log').read_bytes()).hexdigest()==r['log_sha256']
assert '0 passed; 1 failed;' in Path('/tmp/sail-sdp-catalog-analysis-boundary-control.log').read_text()
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-catalog-analysis-boundary-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence');qualified='/tmp/sail-sdp-catalog-analysis-boundary-public/receipt.json'
for packet,output in [('wrapped-catalog-identifier','phases'),('constant-context-lowering','arithmetic'),('identifier-function-provenance','provenance')]:
 subprocess.run([PYTHON,str(p/packet/'run-probe.py'),'/tmp/sail-sdp-catalog-analysis-boundary-'+output,c['commit'],qualified,'identifier'],check=True)
print('PASS exact-source wrapped catalog public and focused probes',flush=True)
