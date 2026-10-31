from pathlib import Path
import json,os,subprocess,tempfile,hashlib
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
base=json.loads(Path('/tmp/sail-sdp-numeric-divisor-candidate.json').read_text())['commit']
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
for kind,path,package,pattern,test in [
 ('duplicate','crates/sail-plan/src/function/scalar/math.rs','sail-plan','volatile_numeric_divisor_is_evaluated_once','crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs'),
 ('codec','crates/sail-execution/src/proto/codec.rs','sail-execution','numeric_divisor_codec_preserves_kind_mode_and_execution','crates/sail-execution/src/proto/codec/zero_division_tests.rs')]:
 source=git('show',base+':'+path)
 if kind=='duplicate':
  prior=git('show',base+'^:'+path)
  begin=prior.index('fn make_safe_divisor(');end=prior.index('\n/// Arguments:',begin)
  start=source.index('fn make_safe_divisor(');finish=source.index('\n/// Arguments:',start)
  source=source[:start]+prior[begin:end]+source[finish:]
 else:
  start=source.index('            "spark_divisor_ansi_divide" =>');end=source.index('            "random_poisson" =>',start);source=source[:start]+source[end:]
 blob=git('hash-object','-w','--stdin',input=source+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: remove numeric divisor '+kind+' fix')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/numeric-divisor-'+kind,control)
 assert git('diff','--name-only',base,control)==path
 assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p',package,'--lib','--locked',pattern,'--','--nocapture']
 log=Path('/tmp/sail-sdp-numeric-divisor-'+kind+'-control.log')
 runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
 with log.open('x') as output:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=output,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-numeric-divisor-'+kind+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':command,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print('PASS unchanged '+kind+' regression control:0 passed/1 failed',flush=True)
