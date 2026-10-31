from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-flow-insert-policy-01-candidate.json').read_text());base=c['commit']
assert json.loads(Path('/tmp/sail-sdp-flow-insert-policy-01-gate.json').read_text())['outcome']=='passed'
path='crates/sail-sql-analyzer/src/pipeline.rs';test_path='crates/sail-sql-analyzer/src/pipeline/tests/flow_policy.rs'
for label in ['message','precedence']:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 s=git('show',base+':'+path)
 if label=='message':
  before='Some("INSERT OVERWRITE flows not supported.")';after='Some("Only INSERT INTO by name flows supported.")';assert s.count(before)==1;s=s.replace(before,after)
 else:
  before='''            let message = if partition.is_some() {
                Some("Partition spec may not be specified for flow target.")
            } else if matches!(columns, Some(Either::Right(_))) {
                Some("Column schema may not be specified for flow target.")'''
  after='''            let message = if matches!(columns, Some(Either::Right(_))) {
                Some("Column schema may not be specified for flow target.")
            } else if partition.is_some() {
                Some("Partition spec may not be specified for flow target.")'''
  assert s.count(before)==1;s=s.replace(before,after)
 blob=git('hash-object','-w','--stdin',input=s);fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
 try:
  env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: Flow policy '+label)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/flow-policy-'+label+'-control',control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p','sail-sql-analyzer','--lib','--locked','flow_insert_policy_preserves_messages_and_precedence'];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-flow-policy-'+label+'-control.log')
 with log.open('x')as out:result=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-flow-policy-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':cmd,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;'in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True);print('PASS unchanged Flow-policy '+label+' control0of1',flush=True)
