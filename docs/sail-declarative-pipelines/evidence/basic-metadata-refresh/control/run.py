from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate';label='metadata-basic-02'
def git(*args,**kw):return subprocess.check_output(['git','-C',R,*args],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());base=c['commit']
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert g.get('outcome')=='passed' and g['sail_commit']==base
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
path='crates/sail-spark-connect/src/pipelines/materialize.rs';test_path='crates/sail-spark-connect/src/pipelines/materialize/tests/basic.rs'
s=git('show',base+':'+path);old='if old.comment != column.comment {';assert s.count(old)==1
blob=git('hash-object','-w','--stdin',input=s.replace(old,'if old.comment != column.comment && column.comment.is_some() {'))
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
try:
 env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: omit pipeline column comment removal')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/metadata-basic-comment-control',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','basic_metadata_refresh_preserves_exact_schema_and_updates_then_removes_comments']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
log=Path('/tmp/sail-sdp-metadata-basic-comment-control.log')
with log.open('x')as f:r=subprocess.run(command,cwd=G,env=env,stdout=f,stderr=subprocess.STDOUT)
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':command,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
Path('/tmp/sail-sdp-metadata-basic-comment-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert r.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-4000:]
subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
print('PASS unchanged original basic control: missing comment removal fails the third state',flush=True)
