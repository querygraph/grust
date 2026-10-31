from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,tempfile,sys
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate');label=sys.argv[1]
candidate=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());base=candidate['commit']
receipt=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert receipt['sail_commit']==base and receipt['outcome']=='passed'
path='crates/sail-data-source/src/listing/source.rs';test='crates/sail-data-source/src/listing/schema_validation_tests.rs'
def git(*args,**kwargs):return subprocess.check_output(['git','-C',str(root),*args],text=True,**kwargs).strip()
assert subprocess.check_output(['git','-C',str(gate),'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',str(gate),'status','--porcelain'],text=True).strip()
src=git('show',base+':'+path)
line='use sail_common_datafusion::schema_validation::validate_field_names;'
assert src.count(line)==1;src=src.replace(line+'\n','')
src,count=re.subn(r'^\s*validate_field_names\((?:schema.fields\(\)|&partition_fields), read_case_sensitive\)\?;\n','',src,flags=re.M)
assert count==3,count
blob=git('hash-object','-w','--stdin',input=src+'\n')
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
 tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass listing data and partition schema checks')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/listing-source-schema-check',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-data-source','--lib','--locked','listing::source::schema_validation_tests']
runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
log=Path('/tmp/sail-sdp-listing-schema-control.log')
with log.open('w') as out:result=subprocess.run(command,cwd=gate,env=runenv,stdout=out,stderr=subprocess.STDOUT)
report={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'changed_path':path,'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)}
Path('/tmp/sail-sdp-listing-schema-control.json').write_text(json.dumps(report,indent=2)+'\n')
assert result.returncode==101 and '0 passed; 3 failed;' in log.read_text(),log.read_text()[-2500:]
subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
print('PASS unchanged listing control: all three unchanged file/supplied/partition guard tests fail without validation',flush=True)
