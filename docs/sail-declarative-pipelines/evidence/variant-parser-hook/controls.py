from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
base=json.loads(Path('/tmp/sail-sdp-variant-parser-hook-04-candidate.json').read_text())['commit']
assert json.loads(Path('/tmp/sail-sdp-variant-parser-hook-04-gate.json').read_text())['outcome']=='passed'
path='crates/sail-sql-macro/src/tree/parser.rs'
for label,package,test_path,test in [
 ('dispatch','sail-sql-parser','crates/sail-sql-parser/src/tree/parser/tests.rs','custom_variant_forwards_dependency_and_options'),
 ('field-guard','sail-sql-macro','crates/sail-sql-macro/src/tree/parser/tests.rs','custom_variant_rejects_ignored_field_parser_attributes')]:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 s=git('show',base+':'+path)
 if label=='dispatch':
  before='return Ok(quote! { { let f = #function; f(args.clone(), options) } });'
  after='return Ok(quote! { { let f = #function; f(args.clone(), options).filter(|_| false) } });'
 else:
  before='''        for field in &variant.fields {
            AttributeExtractor::try_new(ATTRIBUTE, &field.attrs)?.expect_empty()?;
        }''';after=''
 assert s.count(before)==1;s=s.replace(before,after)
 blob=git('hash-object','-w','--stdin',input=s);fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
 try:
  env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: custom variant '+label)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/variant-hook-'+label+'-control',control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 cmd=['cargo','+1.98.1','test','-p',package,'--lib','--locked',test];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-variant-hook-'+label+'-control.log')
 with log.open('x')as out:result=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-variant-hook-'+label+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':cmd,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;'in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True);print('PASS unchanged variant hook '+label+' control0of1',flush=True)
