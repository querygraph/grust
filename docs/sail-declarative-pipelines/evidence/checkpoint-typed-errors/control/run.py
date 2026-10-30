from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,os,tempfile,hashlib
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';c=json.loads(Path('/tmp/sail-sdp-checkpoint-typed-errors-fixed-candidate.json').read_text());p=Path('/tmp/sail-sdp-checkpoint-typed-errors-control');p.mkdir()
def git(*args,**kwargs):return subprocess.check_output(['git','-C',repo,*args],**kwargs)
path='crates/sail-physical-plan/src/remote_checkpoint.rs';base=git('show',c['base']+':'+path);decl=b'\n#[cfg(test)]\n#[path = "remote_checkpoint_cleanup_tests.rs"]\nmod cleanup_error_tests;\n';control=base+decl
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',c['commit'],env=env)
 blob=git('hash-object','-w','--stdin',input=control).decode().strip();git('update-index','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env).decode().strip();sha=git('commit-tree',tree,'-p',c['base'],'-m','control: checkpoint typed-error regression on original implementation').decode().strip()
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/controls/checkpoint-typed-errors',sha)
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
subprocess.run(['git','-C',gate,'checkout','--detach',sha],check=True)
cmd=['cargo','+1.98.1','test','-p','sail-physical-plan','--lib','--locked','remote_checkpoint::cleanup_error_tests::simultaneous_checkpoint_and_cleanup_failures_preserve_nonretryable_cause','--','--exact']
try:
 e={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
 with (p/'test.log').open('w') as out:r=subprocess.run(cmd,cwd=gate,env=e,stdout=out,stderr=subprocess.STDOUT)
 receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':c['base'],'candidate':c['commit'],'control':sha,'base_production_sha256':hashlib.sha256(base).hexdigest(),'control_without_test_declaration_sha256':hashlib.sha256(control[:-len(decl)]).hexdigest(),'test_only_declaration':decl.decode(),'command':cmd,'exit_code':r.returncode}
 (p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');log=(p/'test.log').read_text();assert r.returncode==101 and '0 passed; 1 failed;' in log and 'CommitStateUnknown' in log,log
 print(log[-2300:]);print('PASS expected typed-cause regression failure on original production')
finally:subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
