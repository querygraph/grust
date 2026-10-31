from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib,tempfile,os
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-candidate.json').read_text());base=c['commit'];p='crates/sail-plan/src/resolver/expression/cast.rs'
assert json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-gate.json').read_text())['outcome']=='passed'
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('rev-parse',c['base']+':'+p);git('update-index','--cacheinfo','100644,'+blob+','+p,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: restore strict legacy floating casts')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/legacy-floating-cast-control',control)
assert git('diff','--name-only',base,control)==p
tests='crates/sail-plan/src/resolver/expression/cast/tests/floating.rs';assert git('rev-parse',base+':'+tests)==git('rev-parse',control+':'+tests)
subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::expression::cast::tests::floating']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python'}
log=Path('/tmp/sail-sdp-legacy-floating-cast-control.log')
with log.open('x') as out:result=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-legacy-floating-cast-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'path':p,'test_path':tests,'test_blob':git('rev-parse',base+':'+tests),'command':cmd,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 3 failed;' in log.read_text(),log.read_text()[-4000:]
subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
print('PASS unchanged three regression tests fail without resolver branch')
