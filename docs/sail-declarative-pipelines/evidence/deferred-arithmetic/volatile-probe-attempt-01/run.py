from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
base=subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True).strip();assert base=='a49082801e79a6a9cea545186fecb7171d54a4b5'
def git(*a,**kw):return subprocess.check_output(['git','-C',ROOT,*a],text=True,**kw).strip()
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
path='crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs';snippet=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/deferred-arithmetic/volatile-divisor-regression.rs').read_bytes()
source=subprocess.check_output(['git','-C',ROOT,'show',base+':'+path])+snippet
blob=git('hash-object','-w','--stdin',input=source.decode());fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);probe=git('commit-tree',tree,'-p',base,'-m','Regression probe: volatile divisor evaluation cardinality')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/volatile-divisor-regression',probe)
assert git('diff','--name-only',base,probe)==path
subprocess.run(['git','-C',GATE,'checkout','--detach',probe],check=True)
command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','volatile_divisor_is_evaluated_once_regression_probe']
log=Path('/tmp/sail-sdp-volatile-divisor-probe.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-volatile-divisor-probe.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'probe':probe,'test_path':path,'parent_test_blob':git('rev-parse',base+':'+path),'probe_test_blob':blob,'snippet_sha256':hashlib.sha256(snippet).hexdigest(),'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text() and 'a divisor must be evaluated once' in log.read_text(),log.read_text()[-4000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('CONFIRMED required volatile-divisor regression:0 pass/1 fail; production branch unchanged',flush=True)
