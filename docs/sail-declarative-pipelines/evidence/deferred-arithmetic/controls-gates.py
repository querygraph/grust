from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-candidate.json').read_text());base=c['commit']
r=json.loads(Path('/tmp/sail-sdp-deferred-arithmetic-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base

def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
for kind,path,package,pattern,test,failed in [
 ('eager','crates/sail-plan/src/function/scalar/math.rs','sail-plan','resolver::identifier::arithmetic_tests::','crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs',2),
 ('codec','crates/sail-execution/src/proto/codec.rs','sail-execution','zero_division_codec_preserves_kind_type_and_structured_failure','crates/sail-execution/src/proto/codec/zero_division_tests.rs',1),
]:
 s=git('show',base+':'+path)
 if kind=='eager':
  start=s.index('fn spark_div(');pos=s.index('    let (dividend, divisor) = arguments.two()?;',start)+len('    let (dividend, divisor) = arguments.two()?;')
  s=s[:pos]+'''
    if function_context.constant_context == crate::function::constant_context::ConstantContext::Ordinary
        && matches!(&divisor, Expr::Literal(ScalarValue::Int32(Some(0)), _)) {
        return Err(PlanError::ArrowError(datafusion::arrow::error::ArrowError::DivideByZero));
    }
''' +s[pos:]
 else:
  start=s.index('            "spark_divide_by_zero" =>');end=s.index('            "random_poisson" =>',start);s=s[:start]+s[end:]
 blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: restore arithmetic '+kind+' failure')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/deferred-arithmetic-'+kind,control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
 assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
 subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p',package,'--lib','--locked',pattern]
 log=Path('/tmp/sail-sdp-deferred-arithmetic-'+kind+'-control.log')
 runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
 with log.open('w') as out:result=subprocess.run(command,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-deferred-arithmetic-'+kind+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':command,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_path':test,'test_blob':git('rev-parse',base+':'+test),'failed':failed},indent=2)+'\n')
 passed = 1 if kind=='eager' else 0
 assert result.returncode==101 and f'{passed} passed; {failed} failed;' in log.read_text(),log.read_text()[-4000:]
 subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
 print(f'PASS unchanged {kind} control:{passed} pass/{failed} fail',flush=True)
