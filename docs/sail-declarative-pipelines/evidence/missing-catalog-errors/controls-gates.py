from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-missing-catalog-candidate.json').read_text());base=c['commit']
r=json.loads(Path('/tmp/sail-sdp-missing-catalog-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base

def git(*args,**kwargs):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kwargs).strip()
for kind,path,start_text,end_text,new in [
 ('diagnostic', 'crates/sail-common-datafusion/src/error/catalog.rs', '        condition: "CATALOG_NOT_FOUND".into(),\n', '        sql_state:', '        condition: "CONTROL_CATALOG_ERROR".into(),\n'),
 ('hierarchy', 'crates/sail-spark-connect/src/error.rs', '    let classes = match class {\n', '    metadata.insert("classes".into(), classes);', '    let classes = format!("[\\"{class}\\"]");\n'),
]:
 s=git('show',base+':'+path);start=s.index(start_text);end=s.index(end_text,start);s=s[:start]+new+s[end:]
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
  tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: remove missing catalog '+kind+' preservation')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/missing-catalog-'+kind,control)
 test='crates/sail-spark-connect/src/error/structured/tests.rs'
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','missing_catalog_execution_errors_keep_spark_metadata']
 log=Path('/tmp/sail-sdp-missing-catalog-'+kind+'-control.log')
 runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
 with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-missing-catalog-'+kind+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':command,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print('PASS unchanged missing catalog '+kind+' control:0 pass/1 fail',flush=True)
