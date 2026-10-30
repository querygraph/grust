from datetime import datetime, timezone
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal')
gate=Path('/Users/alexy/src/sail-sdp-gate')
out=Path('/tmp/sail-sdp-scope-reentrant-control')
out.mkdir()
def git(*args,**kw):
 return subprocess.check_output(['git','-C',str(root),*args],**kw)
base=git('rev-parse','HEAD').decode().strip()
path='crates/sail-common-datafusion/src/task_resources_tests.rs'
source=(root/path).read_text()
addition=source[source.index('struct ReentrantCancellation'):source.index('#[tokio::test]\nasync fn panicking_supervisor')]
tests=git('show',base+':'+path)+b'\n'+addition.encode()
blob=git('hash-object','-w','--stdin',input=tests).decode().strip()
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env)
 git('update-index','--add','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env).decode().strip()
 commit=git('commit-tree',tree,'-p',base,'-m','test: reproduce reentrant resource cancellation under original lock').decode().strip()
finally:Path(index).unlink(missing_ok=True)
subprocess.run(['git','-C',str(gate),'checkout','--detach',commit],check=True)
command=['cargo','+1.98.1','test','-p','sail-common-datafusion','--lib','--locked','cancellation_wakes_reentrant_listeners_after_sealing_and_unlocking','--','--exact']
# Qualified Rust test identity is needed when using --exact.
command[command.index('cancellation_wakes_reentrant_listeners_after_sealing_and_unlocking')]='task_resources::tests::cancellation_wakes_reentrant_listeners_after_sealing_and_unlocking'
env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':str(root/'.venv/bin/python')}
with (out/'test.log').open('w') as log:
 result=subprocess.run(command,cwd=gate,env=env,stdout=log,stderr=subprocess.STDOUT)
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'commit':commit,'command':command,'exit_code':result.returncode,'test_log_sha256':hashlib.sha256((out/'test.log').read_bytes()).hexdigest(),'scope':'Only new reentrant-waker regression on unchanged production source; expected failure, no branch advance'}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(out/'control.patch').write_bytes(git('diff',base,commit))
assert result.returncode==101,(out/'test.log').read_text()
assert '1 failed' in (out/'test.log').read_text()
assert 'assertion failed: !watcher.lock_held.load(Ordering::SeqCst)' in (out/'test.log').read_text()
git('update-ref','refs/sdp/controls/resource-reentrant-cancellation',commit,'0'*40)
print('Confirmed original lock-order regression at '+commit)
print((out/'test.log').read_text()[-3000:])
