from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
base='c1befda7a8f29937c9bbc32d3f516379732e9eae'
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
path='crates/sail-function/src/scalar/math/div_mod_lazy_tests.rs';snippet=Path('/tmp/sail-sdp-lazy-divmod-batch-probe.rs').read_bytes();source=subprocess.check_output(['git','-C',ROOT,'show',base+':'+path])+snippet
blob=git('hash-object','-w','--stdin',input=source.decode());fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);probe=git('commit-tree',tree,'-p',base,'-m','Probe: isolate operand evaluation stages')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/lazy-divmod-batch-probe-v2',probe)
subprocess.run(['git','-C',GATE,'checkout','--detach',probe],check=True)
command=['cargo','+1.98.1','test','-p','sail-function','--lib','--locked','selected_batch_error_and_cost_probe','--','--nocapture']
log=Path('/tmp/sail-sdp-lazy-divmod-batch-probe-v2.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-lazy-divmod-batch-probe-v2.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'probe':probe,'path':path,'snippet_sha256':hashlib.sha256(snippet).hexdigest(),'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
assert result.returncode==0,log.read_text()[-4000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('PASS stage diagnostic; production unchanged')
