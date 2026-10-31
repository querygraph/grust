from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-decimal-codec-candidate.json').read_text());base=c['commit'];path='crates/sail-execution/src/proto/codec.rs';test_path='crates/sail-execution/src/proto/codec/decimal_string_cast_tests.rs'
r=json.loads(Path('/tmp/sail-sdp-decimal-codec-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
for name in ['fail-policy','range-policy','signed-scale','precision-range','scale-range']:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 source=git('show',base+':'+path)
 start=source.index('            UdfKind::SparkStringToDecimal(r#gen::SparkStringToDecimalUdf {');end=source.index('            UdfKind::SparkStructRename(',start);block=source[start:end]
 if name in ['fail-policy','range-policy']:
  flag='fail_on_error' if name=='fail-policy' else 'allow_negative_scale'
  call_start=block.index('SparkStringToDecimal::try_new(');head,call=block[:call_start],block[call_start:]
  old='                    '+flag+',';assert call.count(old)==1;call=call.replace(old,'                    '+flag+' & false,');block=head+call
 elif name=='precision-range':
  a=block.index('                let precision = u8::try_from(');b=block.index('                let scale =',a)
  block=block[:a]+'                let precision = precision as u8;\n'+block[b:]
 elif name=='scale-range':
  a=block.index('                let scale = i8::try_from(');b=block.index('                return Ok(',a)
  block=block[:a]+'                let scale = scale as i8;\n'+block[b:]
 source=source[:start]+block+source[end:]
 if name=='signed-scale':
  old='scale: i32::from(func.scale()),';assert source.count(old)==1;source=source.replace(old,'scale: i32::from(func.scale()).abs(),')
 blob=git('hash-object','-w','--stdin',input=source+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: disable decimal wire '+name)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/decimal-codec-'+name,control)
 assert git('diff','--name-only',base,control)==path
 assert git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 test='decimal_codec_rejects_malformed_and_out_of_range_fields' if name.endswith('-range') else 'decimal_codec_preserves_all_captured_fields_and_values'
 command=['cargo','+1.98.1','test','-p','sail-execution','--lib','--locked',test]
 env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python'}
 log=Path('/tmp/sail-sdp-decimal-codec-'+name+'-control.log')
 with log.open('x') as out:result=subprocess.run(command,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-decimal-codec-'+name+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
 print('PASS unchanged decimal wire '+name+' control0/1',flush=True)
