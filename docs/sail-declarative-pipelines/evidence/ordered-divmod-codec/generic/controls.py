from pathlib import Path
import json,os,tempfile,subprocess,hashlib
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
base=json.loads(Path('/tmp/sail-sdp-staged-lambda-decoder-candidate.json').read_text())['commit'];path='crates/sail-execution/src/proto/converter.rs';test='crates/sail-execution/src/proto/converter/staged_lambda_tests.rs'
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
for name,pattern in [('retention','partial_none_keeps_previous_lambda_outputs'),('limit','resolution_includes_zero_and_last_allowed_steps'),('prefix','parameter_counts_preserve_physical_optional_lambda_prefixes')]:
 s=git('show',base+':'+path)
 if name=='retention':
  a='// None means no new information; retain any prior field/body.';assert s.count(a)==1;s=s.replace(a,'decoded_values[index] = None; value_or_lambda[index] = ValueOrLambda::Lambda(None);')
 elif name=='limit':
  a='0..=fun.signature().lambda_parameters_max_iterations';assert s.count(a)==1;s=s.replace(a,'0..fun.signature().lambda_parameters_max_iterations')
 else:
  a='complete && param_sets.len() < num_lambdas';assert s.count(a)==1;s=s.replace(a,'complete && param_sets.len() != num_lambdas')
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: regress staged lambda '+name)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/staged-lambda-'+name,control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p','sail-execution','--lib','--locked',pattern,'--','--nocapture'];log=Path('/tmp/sail-sdp-staged-lambda-decoder-'+name+'-control.log')
 runenv={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
 with log.open('x') as out:r=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-staged-lambda-decoder-'+name+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test,'test_blob':git('rev-parse',base+':'+test),'command':command,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert r.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print('PASS unchanged staged '+name+' control0/1',flush=True)
