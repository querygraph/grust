from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
base=json.loads(Path('/tmp/sail-sdp-late-bound-scope-ready-candidate.json').read_text())['commit']
r=json.loads(Path('/tmp/sail-sdp-late-bound-scope-ready-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
for check in r['checks']: assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
def git(*a,**kw):return subprocess.check_output(['git','-C',str(root),*a],text=True,**kw).strip()
def gate_git(*a):return subprocess.check_output(['git','-C',str(gate),*a],text=True).strip()
path='crates/sail-plan/src/resolver/query/read.rs';test='crates/sail-plan/src/resolver/query/late_bound_scope_tests.rs'
original=git('show',base+':'+path)
changes=[('lookup', 'Some(scope) if late_bound => scope.resolve_late_bound(&reference)?,','Some(scope) if late_bound => scope.resolve(&reference)?,'),('namespace','Some(scope) if late_bound => scope.qualify_late_bound(&reference)?,','Some(scope) if late_bound => scope.qualify(&reference)?,')]
for label,old,new in changes:
 assert original.count(old)==1
 blob=git('hash-object','-w','--stdin',input=original.replace(old,new)+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass late identifier '+label+' policy')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/late-bound-'+label,control)
 assert git('diff','--name-only',base,control)==path
 assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert gate_git('rev-parse','HEAD')==base and not gate_git('status','--porcelain')
 subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','late_bound_scope_tests']
 log=Path('/tmp/sail-sdp-late-bound-'+label+'-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0'}
 with log.open('w') as out:result=subprocess.run(cmd,cwd=gate,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-late-bound-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
 assert result.returncode==101 and '1 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
 print('PASS unchanged late binding '+label+' control: default passes, opt-out fails',flush=True)
