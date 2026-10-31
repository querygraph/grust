from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-identifier-provenance-tree-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-identifier-provenance-tree-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-identifier-provenance-tree-rust.log').read_text())==['140','100','177']
for label in ['builder','udf','type','materialization']:
 r=json.loads(Path('/tmp/sail-sdp-provenance-tree-'+label+'-control.json').read_text());log=Path('/tmp/sail-sdp-provenance-tree-'+label+'-control.log').read_bytes()
 assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['log_sha256'] and f"{r['passed']} passed; {r['failed']} failed;".encode() in log
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-provenance-tree-public'],check=True)
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/identifier-function-provenance');qualified='/tmp/sail-sdp-provenance-tree-public/receipt.json'
subprocess.run([PYTHON,str(p/'run-probe.py'),'/tmp/sail-sdp-provenance-tree-candidate',c['commit'],qualified,'identifier'],check=True)
for name,probe in [('validation','reference.py'),('replacement','runtime-replacement-reference.py')]:
 subprocess.run([PYTHON,str(p/'validation-probes/run-probe.py'),'/tmp/sail-sdp-provenance-tree-'+name,c['commit'],qualified,'identifier',probe],check=True)
for kind in ['dynamic','namespace','expression']:
 subprocess.run([PYTHON,str(p/'binding-probes/run-probe.py'),'/tmp/sail-sdp-provenance-tree-'+kind,c['commit'],qualified,kind],check=True)
print('PASS exact-source public, provenance, parameter and previous validation/binding probes complete',flush=True)
