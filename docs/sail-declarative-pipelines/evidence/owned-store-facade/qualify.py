from pathlib import Path
import hashlib,json,subprocess
label='owned-store-qualified-errors';root='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert [x['name'] for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:
 assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '214 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
for name,file,message,count in [
 ('owned-store-final-bypass','owned_store.rs','owner completed before held multipart completion',2),
 ('owned-store-condition-control','owned_store_error.rs','provider condition variant lost:',1),
]:
 r=json.loads(Path('/tmp/sail-sdp-'+name+'-receipt.json').read_text());log=Path(r['log']).read_bytes()
 assert r['fixed_commit']==c['commit'] and r['exit_code']==101
 assert hashlib.sha256(log).hexdigest()==r['sha256']
 assert log.count(message.encode())==count and f'0 passed; {count} failed;'.encode() in log
 assert git('diff','--name-only',r['commit'],c['commit'])=='crates/sail-execution/src/'+file
 for path in c['paths']:
  if path.endswith('_tests.rs'):
   assert git('rev-parse',r['commit']+':'+path)==git('rev-parse',c['commit']+':'+path)
p=Path('/tmp/sail-sdp-'+label+'-sail-execution-release');r=json.loads((p/'receipt.json').read_text())
assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '12 passed; 0 failed;' in (p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
assert all(p.startswith('crates/sail-execution/src/') for p in c['paths'])
fixture='crates/sail-execution/src/owned_multipart_test_upload.rs'
assert git('rev-parse',c['base']+':'+fixture)==git('rev-parse',c['commit']+':'+fixture)
old=git('show',c['base']+':crates/sail-execution/src/owned_multipart_tests.rs')
new=git('show',c['commit']+':crates/sail-execution/src/owned_multipart_tests.rs')
fixture_import='use fixture::{Gate, Injected, State, Upload};\n'
assert old.count(fixture_import)==new.count(fixture_import)==1
assert old.replace('#[path = "owned_multipart_test_upload.rs"]\nmod fixture;','use crate::owned_multipart_test_upload as fixture;').replace(fixture_import,'')==new.replace(fixture_import,'')
print('PASS exact facade candidate, 214 library +12 optimized tests, unchanged ownership/condition controls, shared fixture and dependency footprint '+c['commit'])
