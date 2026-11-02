from pathlib import Path
import hashlib,json,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='scoped-session-qualified'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
for x in g['checks']:assert x['exit_code']==0 and sha(x['log'])==x['sha256']
assert '129 passed; 0 failed;'in Path(g['checks'][-1]['log']).read_text()
for name in ['scoped-session-runtime-bypass','scoped-session-builder-rebuild']:
 r=json.loads(Path('/tmp/sail-sdp-'+name+'-receipt.json').read_text());assert r['fixed_commit']==c['commit']
 assert git('diff','--name-only',r['commit'],c['commit'])=='crates/sail-common-datafusion/src/session/scoped.rs'
 test='crates/sail-common-datafusion/src/session/scoped/tests.rs';assert git('rev-parse',r['commit']+':'+test)==git('rev-parse',c['commit']+':'+test)
 for x in r['checks']:assert x['exit_code']==101 and sha(x['log'])==x['sha256'] and '0 passed; 1 failed;'in Path(x['log']).read_text()
 if name.endswith('runtime-bypass'):
  log=Path(r['checks'][0]['log']).read_text();assert '112, 97, 114, 101, 110, 116'in log and '99, 104, 105, 108, 100'in log
 else:
  assert "Prepared statement 'scoped_prepared' does not exist"in Path(r['checks'][0]['log']).read_text()
  assert 'Arc::ptr_eq'in Path(r['checks'][1]['log']).read_text()
p=Path('/tmp/sail-sdp-'+label+'-sail-common-datafusion-release');r=json.loads((p/'receipt.json').read_text());assert r['commit']==c['commit'] and r['outcome']=='passed' and r['test_exit']==r['build_exit']==0
assert len(r['load_pids'])==r['logical_cpus']==len(r['load_worker_exit_codes'])and all(x is not None for x in r['load_worker_exit_codes'])
assert sha(r['binary'])==r['binary_sha256'] and '129 passed; 0 failed;'in(p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths']) and len(c['paths'])==3
assert git('diff',c['base'],c['commit'],'--','Cargo.lock','Cargo.toml')==''
print('PASS exact ScopedSession source, 129 library/optimized tests and three unchanged negative controls '+c['commit'])
