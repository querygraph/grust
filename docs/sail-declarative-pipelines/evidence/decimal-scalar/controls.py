from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-decimal-scalar-candidate.json').read_text());base=c['commit'];prefix='crates/sail-function/src/scalar/spark_string_to_decimal'
r=json.loads(Path('/tmp/sail-sdp-decimal-scalar-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
controls=[
 ('rounding',prefix+'/parse.rs','d >= 5','d >= 6','spark_421_contract_matches_scalars_and_arrays_for_all_string_layouts'),
 ('trim',prefix+'/parse.rs',".trim_matches(|c| c <= '\\u{20}')",'.trim()','spark_421_contract_matches_scalars_and_arrays_for_all_string_layouts'),
 ('policy',prefix+'.rs','self.scale, self.allow_negative_scale)','self.scale, false)','spark_421_negative_scale_policy_contract_matches_all_string_layouts'),
 ('nullable',prefix+'.rs','.with_nullable(true)','.with_nullable(input.is_nullable())','fields_are_nullable_type_only_and_preserve_nonextension_metadata'),
]
for name,path,old,new,test in controls:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 source=git('show',base+':'+path);assert source.count(old)==1,(name,old);source=source.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=source+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: disable decimal '+name+' contract')
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/decimal-scalar-'+name+'-control',control)
 assert git('diff','--name-only',base,control)==path
 tests=[prefix+'/tests.rs',prefix+'/tests/boundaries.rs',prefix+'/tests/contract.json',prefix+'/tests/policy-contract.json',prefix+'/tests/digit-mapping.json']
 for t in tests:assert git('rev-parse',base+':'+t)==git('rev-parse',control+':'+t)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p','sail-function','--lib','--locked',test]
 env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python'}
 log=Path('/tmp/sail-sdp-decimal-scalar-'+name+'-control.log')
 with log.open('x') as out:result=subprocess.run(command,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-decimal-scalar-'+name+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_blobs':{t:git('rev-parse',base+':'+t) for t in tests},'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
 print('PASS unchanged decimal '+name+' control0/1',flush=True)
