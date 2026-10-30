from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
packet=Path('/tmp/sail-sdp-checkpoint-registry-control');packet.mkdir()
c=json.loads(Path('/tmp/sail-sdp-checkpoint-registry-recovery-candidate.json').read_text())
def git(*args,**kwargs):return subprocess.check_output(['git','-C',str(root),*args],**kwargs)
path='crates/sail-cache/src/remote_checkpoint.rs'
base=git('show',c['base']+':'+path)
module=b'\n#[cfg(test)]\n#[path = "remote_checkpoint_tests.rs"]\nmod cleanup_tests;\n'
control=base+module
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',c['commit'],env=env)
 blob=git('hash-object','-w','--stdin',input=control).decode().strip()
 git('update-index','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env).decode().strip()
 commit=git('commit-tree',tree,'-p',c['base'],'-m','Control: checkpoint cleanup recovery tests on unchanged production code').decode().strip()
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/controls/checkpoint-registry-recovery',commit)
assert git('show',commit+':'+path)==control and control[:-len(module)]==base
for unchanged in ('crates/sail-cache/src/lib.rs','crates/sail-object-store/src/path.rs'):
 assert git('show',commit+':'+unchanged)==git('show',c['base']+':'+unchanged)
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':c['base'],'fixed_candidate':c['commit'],'control_commit':commit,'production_path':path,'base_production_sha256':hashlib.sha256(base).hexdigest(),'control_production_without_test_module_sha256':hashlib.sha256(control[:-len(module)]).hexdigest(),'test_only_module_declaration':module.decode(),'scope':'Original registry implementation with only test module/dependencies added; expected failure proves lost metadata after partial storage deletion'}
command=['cargo','+1.98.1','test','-p','sail-cache','--lib','--locked','remote_checkpoint::cleanup_tests::partial_delete_failure_retains_descriptor_for_explicit_retry','--','--exact']
receipt['command']=command
(packet/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(packet/'control.patch').write_bytes(git('diff','--binary',c['base'],commit))
assert subprocess.check_output(['git','-C',str(gate),'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',str(gate),'status','--porcelain'])
subprocess.run(['git','-C',str(gate),'checkout','--detach',commit],check=True)
try:
 env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv'}
 with (packet/'test.log').open('w') as log:r=subprocess.run(command,cwd=gate,env=env,stdout=log,stderr=subprocess.STDOUT)
 receipt['exit_code']=r.returncode;receipt['completed_at']=datetime.now(timezone.utc).isoformat()
 receipt['log_sha256']=hashlib.sha256((packet/'test.log').read_bytes()).hexdigest()
 receipt['expected_failure_observed']=r.returncode==101 and 'cleanup discarded recovery metadata' in (packet/'test.log').read_text() and '0 passed; 1 failed;' in (packet/'test.log').read_text()
 (packet/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 assert subprocess.check_output(['git','-C',str(gate),'rev-parse','HEAD'],text=True).strip()==commit
 assert receipt['expected_failure_observed'],(packet/'test.log').read_text()[-12000:]
 print('PASS expected baseline failure '+commit,flush=True)
finally:
 subprocess.run(['git','-C',str(gate),'checkout','--detach',c['commit']],check=True)
