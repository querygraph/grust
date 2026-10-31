from pathlib import Path
import hashlib,json,os,subprocess,tempfile
from datetime import datetime,timezone
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
base=json.loads(Path('/tmp/sail-sdp-ambiguous-reference-final-candidate.json').read_text())['commit']
path='crates/sail-plan/src/resolver/expression/attribute.rs'
log=Path('/tmp/sail-sdp-ambiguous-reference-control.log')
def git(*args,**kwargs):return subprocess.check_output(['git','-C',str(root),*args],text=True,**kwargs).strip()
assert json.loads(Path('/tmp/sail-sdp-ambiguous-reference-final-gate.json').read_text())['outcome']=='passed'
assert subprocess.check_output(['git','-C',str(gate),'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',str(gate),'status','--porcelain'],text=True).strip()
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env)
 blob=git('rev-parse','005fcb078:'+path)
 git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
 tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bypass structured ambiguity reporting')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/ambiguous-reference-wiring',control)
assert git('diff','--name-only',base,control)==path
test='crates/sail-plan/src/resolver/expression/ambiguous_tests.rs'
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::expression::ambiguous::tests']
runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
with log.open('w') as out:result=subprocess.run(command,cwd=gate,env=runenv,stdout=out,stderr=subprocess.STDOUT)
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'changed_path':path,'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)}
Path('/tmp/sail-sdp-ambiguous-reference-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
assert 'unstructured error: analysis error: ambiguous attribute' in log.read_text()
subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
print('PASS unchanged native SQL control: actual native-resolution test fails without ambiguity wiring',flush=True)
