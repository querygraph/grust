from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';base=json.loads(Path('/tmp/sail-sdp-identifier-provenance-ready-candidate.json').read_text())['commit']
r=json.loads(Path('/tmp/sail-sdp-identifier-provenance-ready-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
def git(*a,**kw):return subprocess.check_output(['git','-C',ROOT,*a],text=True,**kw).strip()
mutations=[
 ('builder','crates/sail-plan/src/function/common.rs','                *foldable = false;','                *foldable = true;',1,2),
 ('typeof','crates/sail-plan/src/resolver/expression/function.rs','''            let mut scope = state.suspend_foldability();
            self.resolve_expressions_and_names(arguments, schema, scope.state())
                .await?''','''            self.resolve_expressions_and_names(arguments, schema, state).await?''',1,2),
 ('udf','crates/sail-plan/src/resolver/expression/function.rs','if (registered || is_higher_order_function(&canonical_function_name))','if false',2,1),
 ('parent','crates/sail-plan/src/resolver/state/foldability.rs','self.state.foldability = self.previous;','self.state.foldability = self.previous.map(|_| true);',1,2),
]
for label,path,old,new,passed,failed in mutations:
 s=git('show',base+':'+path);assert s.count(old)==1,(label,s.count(old));s=s.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass scalar identifier '+label+' provenance')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/identifier-provenance-'+label,control)
 test='crates/sail-plan/src/resolver/identifier/provenance_tests.rs';assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::identifier::provenance_tests::']
 log=Path('/tmp/sail-sdp-provenance-'+label+'-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python'}
 with log.open('w') as out:result=subprocess.run(cmd,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-provenance-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test),'passed':passed,'failed':failed},indent=2)+'\n')
 assert result.returncode==101 and f'{passed} passed; {failed} failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print(f'PASS unchanged provenance {label} control:{passed} pass/{failed} fail',flush=True)
