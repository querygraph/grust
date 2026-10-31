from pathlib import Path
import hashlib,json,re,subprocess
PYTHON='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python';GATE='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-gate.json').read_text())
assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-deferred-arithmetic-rust.log').read_text())==['229','394','106','180']
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence')
baseline=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-baseline-runtime/receipt.json').read_text())
assert baseline['before']==baseline['after'] and baseline['before']['sail_commit']==c['base']
assert baseline['before']['probe_sha256']==hashlib.sha256((p/'deferred-arithmetic/runtime-gap-reference.py').read_bytes()).hexdigest()
assert baseline['server_exit_code']==baseline['probe_exit_code']==0 and baseline['remaining_listener_pids']==[]
subprocess.run([PYTHON,'/tmp/sail-sdp-deferred-arithmetic-controls.py'],check=True)
for kind,failed in [('eager',2),('codec',1)]:
 r=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-'+kind+'-control.json').read_text());log=Path('/tmp/sail-sdp-deferred-arithmetic-'+kind+'-control.log').read_bytes()
 assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['log_sha256'] and f'{1 if kind=="eager" else 0} passed; {failed} failed;'.encode() in log
subprocess.run([PYTHON,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-deferred-arithmetic-public'],check=True)
qualified='/tmp/sail-sdp-deferred-arithmetic-public/receipt.json'
for packet,output,probe in [('deferred-arithmetic','candidate-schema','schema-reference.py'),('deferred-arithmetic','candidate-runtime','runtime-gap-reference.py'),('wrapped-catalog-identifier','phases','reference.py'),('constant-context-lowering','arithmetic','reference.py'),('identifier-function-provenance','provenance','reference.py')]:
 subprocess.run([PYTHON,str(p/packet/'run-probe.py'),'/tmp/sail-sdp-deferred-arithmetic-'+output,c['commit'],qualified,'identifier',probe],check=True)
print('PASS exact-source deferred arithmetic public/probes; runtime gaps retained',flush=True)
