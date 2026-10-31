from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-unsupported-pipeline-ctas-02-candidate.json').read_text());base=c['commit']
assert json.loads(Path('/tmp/sail-sdp-unsupported-pipeline-ctas-02-gate.json').read_text())['outcome']=='passed'
for label,path,test_path,package,test in [
 ('producer','crates/sail-sql-analyzer/src/pipeline.rs','crates/sail-sql-analyzer/src/pipeline/tests/unsupported.rs','sail-sql-analyzer','ordinary_ctas_is_rejected_only_by_pipeline_normalization'),
 ('message','crates/sail-spark-connect/src/pipelines/sql.rs','crates/sail-spark-connect/src/pipelines/sql/tests/unsupported.rs','sail-spark-connect','original_unsupported_ctas_uses_registration_message_and_source')]:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 s=git('show',base+':'+path)
 if label=='producer':
  a=s.index('            spec::Plan::Command(spec::CommandPlan {\n                node: spec::CommandNode::CreateTableAsSelect { definition, .. },');b=s.index('            spec::Plan::Command(plan) =>',a);s=s[:a]+s[b:]
 else:
  s=s.replace('            Err(sail_sql_analyzer::error::SqlError::AnalysisError(message)) => {\n                Err(PreparationFailure::Analysis(message))\n            }\n','')
 blob=git('hash-object','-w','--stdin',input=s);fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
 try:
  env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass raw Flow '+label)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/unsupported-ctas-'+label+'-control',control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p',package,'--lib','--locked',test];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-unsupported-ctas-'+label+'-control.log')
 with log.open('x')as out:result=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-unsupported-ctas-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':cmd,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;'in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True);print('PASS unchanged raw-Flow '+label+' control0of1',flush=True)
