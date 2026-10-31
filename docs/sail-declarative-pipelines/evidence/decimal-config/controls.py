from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.load(open('/tmp/sail-sdp-decimal-config-candidate.json'));base=c['commit'];r=json.load(open('/tmp/sail-sdp-decimal-config-gate.json'));assert r['outcome']=='passed' and r['sail_commit']==base
test_path='crates/sail-spark-connect/src/config/decimal_tests.rs'
for name,path,test in [
 ('capture','crates/sail-spark-connect/src/config.rs','decimal_session_and_override_snapshots_keep_independent_semantics'),
 ('set-validation','crates/sail-spark-connect/src/config.rs','invalid_decimal_set_and_override_preserve_prior_session_value'),
 ('java-trim','crates/sail-spark-connect/src/config/boolean.rs','decimal_policy_uses_spark_42_defaults_and_java_boolean_syntax'),
 ('hierarchy','crates/sail-spark-connect/src/error.rs','invalid_decimal_set_and_override_preserve_prior_session_value'),
]:
 assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
 assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
 source=git('show',base+':'+path)
 if name=='capture':old='output.legacy_allow_negative_scale_of_decimal = value;';new='output.legacy_allow_negative_scale_of_decimal = value & false;'
 elif name=='set-validation':old='if key == SparkConfigKey::SPARK_SQL_LEGACY_ALLOW_NEGATIVE_SCALE_OF_DECIMAL {';new='if false && key == SparkConfigKey::SPARK_SQL_LEGACY_ALLOW_NEGATIVE_SCALE_OF_DECIMAL {'
 elif name=='java-trim':old="value.trim_matches(|c| c <= '\\u{20}')";new='value.trim()'
 else:
  a=source.index('        "org.apache.spark.SparkIllegalArgumentException" => format!(');b=source.index('        _ =>',a);old=source[a:b];new=''
 assert source.count(old)==1;source=source.replace(old,new)
 blob=git('hash-object','-w','--stdin',input=source+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: disable decimal config '+name)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/decimal-config-'+name,control)
 assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
 subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
 command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked',test]
 env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
 log=Path('/tmp/sail-sdp-decimal-config-'+name+'-control.log')
 with log.open('x') as out:p=subprocess.run(command,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-decimal-config-'+name+'-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':command,'exit_code':p.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 assert p.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
 subprocess.run(['git','-C',G,'checkout','--detach',base],check=True);print('PASS unchanged config '+name+' control0/1',flush=True)
