from pathlib import Path
import json,os,tempfile,subprocess,hashlib
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
base=json.loads(Path('/tmp/sail-sdp-scoped-constant-validation-candidate.json').read_text())['commit'];path='crates/sail-plan/src/resolver/constant/validation.rs';test='crates/sail-plan/src/resolver/constant/validation_tests.rs'
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
for name,pattern in [('admission','internal_constants_validate_then_evaluate_with_existing_literal_path'),('scope','lambda_bindings_end_at_each_body_and_argument'),('volatile','volatile_and_provenance_descendants_reject_without_invocation'),('async','immutable_async_functions_remain_nonconstant_inside_each_scope')]:
 s=git('show',base+':'+path)
 if name=='admission':a='function.args.len() == 3';b='function.args.len() == 0'
 elif name=='scope':a='parameters.contains(&variable.name)';b='!parameters.is_empty()'
 elif name=='volatile':a='function.func.signature().volatility != Volatility::Volatile';b='true'
 else:a='&& function.func.as_async().is_none()';b=''
 assert s.count(a)==1;s=s.replace(a,b)
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: regress scoped constant '+name)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/scoped-constant-'+name,control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked',pattern,'--','--nocapture'];log=Path('/tmp/sail-sdp-scoped-constant-validation-'+name+'-control.log')
 runenv={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
 with log.open('x') as out:r=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-scoped-constant-validation-'+name+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test,'test_blob':git('rev-parse',base+':'+test),'command':command,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert r.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print('PASS unchanged scoped '+name+' control0/1',flush=True)
