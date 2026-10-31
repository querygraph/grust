from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.load(open('/tmp/sail-sdp-temp-view-qualifiers-candidate.json'));base=c['commit'];g=json.load(open('/tmp/sail-sdp-temp-view-qualifiers-gate.json'));assert g['outcome']=='passed' and g['sail_commit']==base
for name,path,test_path,package,test in [
 ('normalization','crates/sail-sql-analyzer/src/statement/temporary_view.rs','crates/sail-sql-analyzer/src/statement/temporary_view/tests.rs','sail-sql-analyzer','query_view_names_use_spark_session_namespace_normalization'),
 ('pipeline','crates/sail-spark-connect/src/pipelines/sql.rs','crates/sail-spark-connect/src/pipelines/sql/tests/preparation.rs','sail-spark-connect','typed_temp_view_parse_failure_discards_the_draft_without_wrapping'),
]:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 source=git('show',base+':'+path)
 if name=='normalization':
  old='if allowed {';new='if allowed && parts.len() == 1 {'
 else:
  a=source.index('            // Typed parser/normalization errors retain');b=source.index('            Err(error) => Err(PreparationFailure::Analysis',a);old=source[a:b];new=''
 assert source.count(old)==1;source=source.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=source+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
 try:
  env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: disable temporary-view '+name)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/temp-view-'+name+'-control',control)
 assert git('diff','--name-only',base,control)==path
 assert git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p',package,'--lib','--locked',test]
 env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-temp-view-'+name+'-control.log')
 with log.open('x')as out:result=subprocess.run(command,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 Path('/tmp/sail-sdp-temp-view-'+name+'-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-2500:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
 print('PASS unchanged '+name+' control0/1',flush=True)
