from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-catalog-analysis-boundary-candidate.json').read_text());base=c['commit']
r=json.loads(Path('/tmp/sail-sdp-catalog-analysis-boundary-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base

def git(*args,**kwargs):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kwargs).strip()
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
path='crates/sail-spark-connect/src/pipelines/sql.rs';test='crates/sail-spark-connect/src/pipelines/sql/tests/preparation.rs'
s=git('show',base+':'+path)
start=s.index('        Err(SparkError::Structured(error))\n')
end=s.index('        Err(error) => Err(PreparationFailure::Evaluation(error)),',start)
s=s[:start]+s[end:]
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
 tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: let structured analysis errors escape registration')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/catalog-analysis-boundary-control',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','structured_catalog_errors_preserve_registration_boundary']
log=Path('/tmp/sail-sdp-catalog-analysis-boundary-control.log')
runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-catalog-analysis-boundary-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':command,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('PASS unchanged wrapped catalog control:0 pass/1 fail',flush=True)
