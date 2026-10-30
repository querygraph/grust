from pathlib import Path
import hashlib,json,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='preparation-no-stream'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert [x['name'] for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '124 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
r=json.loads(Path('/tmp/sail-sdp-preparation-cancel-reset-control-receipt.json').read_text());log=Path(r['log']).read_bytes()
assert r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['sha256']
assert b'0 passed; 1 failed;' in log and b'before.result().is_err_and' in log
assert git('diff','--name-only',r['commit'],c['commit'])=='crates/sail-common-datafusion/src/managed_stream/preparation.rs'
test='crates/sail-common-datafusion/src/managed_stream/preparation_finish_tests.rs'
assert git('rev-parse',r['commit']+':'+test)==git('rev-parse',c['commit']+':'+test)
p=Path('/tmp/sail-sdp-'+label+'-sail-common-datafusion-release');r=json.loads((p/'receipt.json').read_text())
assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '124 passed; 0 failed;' in (p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths']) and len(c['paths'])==2
assert git('diff',c['base'],c['commit'],'--','Cargo.lock','Cargo.toml')==''
print('PASS exact no-stream finish/cancel, unchanged cancellation-reset control, 124 library/optimized tests '+c['commit'])
