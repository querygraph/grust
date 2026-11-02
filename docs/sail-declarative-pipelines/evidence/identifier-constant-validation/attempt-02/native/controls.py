from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';base=json.loads(Path('/tmp/sail-sdp-identifier-constants-ready-candidate.json').read_text())['commit']
r=json.loads(Path('/tmp/sail-sdp-identifier-constants-ready-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
def git(*a,**kw):return subprocess.check_output(['git','-C',ROOT,*a],text=True,**kw).strip()
mutations=[('phase','crates/sail-plan/src/resolver/identifier.rs','scope.state().config_mut().require_foldable = true;','scope.state().config_mut().require_foldable = false;'),('foldability','crates/sail-plan/src/resolver/identifier.rs','        Self::require_constant_expression(&expression)?;',''),('parameter','crates/sail-plan/src/resolver/expression/misc.rs','        if state.config().require_foldable {','        if false {')]
for label,path,old,new in mutations:
 s=git('show',base+':'+path);assert s.count(old)==1;s=s.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass identifier '+label+' validation')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/identifier-constant-'+label,control)
 test='crates/sail-plan/src/resolver/identifier/tests.rs';assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::identifier::tests::']
 log=Path('/tmp/sail-sdp-identifier-constant-'+label+'-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python'}
 with log.open('w') as out:result=subprocess.run(cmd,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-identifier-constant-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
 assert result.returncode==101 and '2 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print('PASS unchanged identifier '+label+' control:2 pass/1 fail',flush=True)
