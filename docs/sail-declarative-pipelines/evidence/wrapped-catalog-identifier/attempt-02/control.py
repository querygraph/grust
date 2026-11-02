from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-wrapped-catalog-candidate.json').read_text());base=c['commit']
r=json.loads(Path('/tmp/sail-sdp-wrapped-catalog-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base

def git(*args,**kwargs):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kwargs).strip()
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
path='crates/sail-plan/src/resolver/constant.rs';test='crates/sail-plan/src/resolver/constant/tests.rs'
s=git('show',base+':'+path)
old='self.resolve_table_identifier_expr(*expr, &mut PlanResolverState::new())'
assert s.count(old)==1
s=s.replace(old,'self.resolve_unwrapped_catalog_expression(*expr)')
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
 tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: restore catalog identifier policy conflation')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/wrapped-catalog-control',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::constant::tests::wrapped_catalog_type_only_']
log=Path('/tmp/sail-sdp-wrapped-catalog-control.log')
runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-wrapped-catalog-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':command,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 2 failed;' in log.read_text(),log.read_text()[-4000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('PASS unchanged wrapped catalog control:0 pass/2 fail',flush=True)
