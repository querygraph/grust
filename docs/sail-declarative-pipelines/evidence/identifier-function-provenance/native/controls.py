from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';base=json.loads(Path('/tmp/sail-sdp-identifier-provenance-tree-candidate.json').read_text())['commit']
r=json.loads(Path('/tmp/sail-sdp-identifier-provenance-tree-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
def git(*a,**kw):return subprocess.check_output(['git','-C',ROOT,*a],text=True,**kw).strip()
mutations=[
 ('builder','crates/sail-plan/src/function/common.rs','Self::mark_non_foldable(expression)','expression','sail-plan','resolver::identifier::provenance_tests::',1,2),
 ('udf','crates/sail-plan/src/resolver/expression/function.rs','if non_foldable && state.config().constant_context','if false','sail-plan','resolver::identifier::provenance_tests::',2,1),
 ('type','crates/sail-common-datafusion/src/literal/non_foldable.rs','[field] => Ok(field.clone()),','[field] => Ok(std::sync::Arc::new(datafusion::arrow::datatypes::Field::new(field.name(), DataType::Null, field.is_nullable()))),','sail-plan','resolver::identifier::provenance_tests::',1,2),
 ('materialization','crates/sail-common-datafusion/src/literal.rs','if non_foldable::contains_marker(expr)?','if false','sail-common-datafusion','literal::non_foldable::tests::',0,1),
]
for label,path,old,new,package,pattern,passed,failed in mutations:
 s=git('show',base+':'+path);assert s.count(old)==1,(label,s.count(old));s=s.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass expression-local '+label+' provenance')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/provenance-tree-'+label,control)
 test='crates/sail-plan/src/resolver/identifier/provenance_tests.rs' if package=='sail-plan' else 'crates/sail-common-datafusion/src/literal/non_foldable.rs'
 assert git('diff','--name-only',base,control)==path
 if package=='sail-plan':assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p',package,'--lib','--locked',pattern]
 log=Path('/tmp/sail-sdp-provenance-tree-'+label+'-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python'}
 with log.open('w') as out:result=subprocess.run(cmd,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-provenance-tree-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test),'passed':passed,'failed':failed},indent=2)+'\n')
 assert result.returncode==101 and f'{passed} passed; {failed} failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print(f'PASS unchanged expression provenance {label} control:{passed} pass/{failed} fail',flush=True)
