from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
base=json.loads(Path('/tmp/sail-sdp-insert-flow-grammar-04-candidate.json').read_text())['commit']
assert json.loads(Path('/tmp/sail-sdp-insert-flow-grammar-04-gate.json').read_text())['outcome']=='passed'
for label,path,test_path,test in [
 ('flow','crates/sail-sql-parser/src/ast/statement.rs','crates/sail-sql-analyzer/src/parser/syntax_tests.rs','insert_and_flow_syntax_rejects_at_the_reference_token'),
 ('overwrite','crates/sail-sql-parser/src/ast/statement/insert.rs','crates/sail-sql-analyzer/src/parser/syntax_tests.rs','insert_and_flow_syntax_rejects_at_the_reference_token'),
 ('source','crates/sail-sql-analyzer/src/source.rs','crates/sail-sql-analyzer/src/parser/syntax_tests.rs','insert_and_flow_syntax_rejects_at_the_reference_token'),
 ('hint','crates/sail-sql-analyzer/src/error/parser/spark.rs','crates/sail-sql-analyzer/src/error/parser/tests.rs','trailing_statement_token_does_not_invent_an_empty_recovery_hint')]:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 s=git('show',base+':'+path)
 if label=='flow':before='boxed(Insert::parser((), o).rewind().ignore_then(s))';after='boxed(s)'
 elif label=='overwrite':
  before='''partition
                .then(if_not_exists.or_not())
                .or_not()
                .map(|clause| match clause {
                    Some((partition, if_not_exists)) => (Some(partition), if_not_exists),
                    None => (None, None),
                })''';after='partition.or_not().then(if_not_exists.or_not())'
 elif label=='source':before='.map_err(|errors| SqlError::parser_with_source(errors, self.text))?;';after='.map_err(SqlError::parser)?;'
 else:before='if expected.is_empty() || *expects_end_of_input {';after='if expected.is_empty() {'
 assert s.count(before)==(2 if label=='source'else 1);s=s.replace(before,after)
 blob=git('hash-object','-w','--stdin',input=s);fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
 try:
  env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: INSERT Flow '+label)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/insert-flow-'+label+'-control',control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p','sail-sql-analyzer','--lib','--locked',test];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-insert-flow-'+label+'-control.log')
 with log.open('x')as out:result=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-insert-flow-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':cmd,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;'in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True);print('PASS unchanged INSERT-Flow '+label+' control0of1',flush=True)
