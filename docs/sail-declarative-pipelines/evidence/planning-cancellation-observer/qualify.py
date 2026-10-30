from pathlib import Path
import hashlib,json,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='planning-cancellation-observer'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert [x['name'] for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '120 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
r=json.loads(Path('/tmp/sail-sdp-planning-cancel-late-control-receipt.json').read_text());log=Path(r['log']).read_bytes()
assert r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['sha256']
assert b'0 passed; 1 failed;' in log and b'scope.cancelled().now_or_never().is_some()' in log
assert git('diff','--name-only',r['commit'],c['commit'])=='crates/sail-common-datafusion/src/task_resources.rs'
p='crates/sail-common-datafusion/src/task_resources_cancellation_tests.rs'
assert git('rev-parse',r['commit']+':'+p)==git('rev-parse',c['commit']+':'+p)
p=Path('/tmp/sail-sdp-planning-cancellation-observer-qualified-sail-common-datafusion-release')
r=json.loads((p/'receipt.json').read_text())
assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '120 passed; 0 failed;' in (p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
assert len(c['paths'])==2 and all(x.startswith('crates/sail-common-datafusion/src/task_resources') for x in c['paths'])
print('PASS exact latched cancellation, unchanged late-observer control, 120 library/optimized tests and joined load workers '+c['commit'])
