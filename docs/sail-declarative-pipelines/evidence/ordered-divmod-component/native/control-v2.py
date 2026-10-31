from pathlib import Path
import json,hashlib,subprocess,os,tempfile
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
base=json.loads(Path('/tmp/sail-sdp-lazy-divmod-candidate.json').read_text())['commit'];path='crates/sail-function/src/scalar/math/div_mod_lazy.rs';test='crates/sail-function/src/scalar/math/div_mod_lazy_tests.rs'
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
s=git('show',base+':'+path);line='            let left_value = evaluate_lambda_rows(left, &[row])?;\n';assert s.count(line)==1;s=s.replace(line,'').replace('            let right_value = evaluate_lambda_rows(right, &[row])?;',line+'            let right_value = evaluate_lambda_rows(right, &[row])?;')
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: evaluate DivMod left before right')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/lazy-divmod-left-first-v2',control)
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
assert git('diff','--name-only',base,control)==path
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-function','--lib','--locked','right_first_null_zero_skip_and_no_replay','--','--nocapture'];log=Path('/tmp/sail-sdp-lazy-divmod-left-first-control-v2.log')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('x') as out:r=subprocess.run(command,cwd=GATE,env=env,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-lazy-divmod-left-first-control-v2.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':r.returncode,'command':command,'test_path':test,'test_blob':git('rev-parse',base+':'+test),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
assert r.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('PASS unchanged right-first control0/1',flush=True)
