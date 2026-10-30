from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,os,tempfile,hashlib
root=Path('/Users/alexy/src/sail-sdp-gate')
candidate=json.loads(Path('/tmp/sail-sdp-execution-owned-multipart-qualified-candidate.json').read_text())
gate=json.loads(Path('/tmp/sail-sdp-execution-owned-multipart-qualified-gate.json').read_text())
assert gate['outcome']=='passed' and gate['sail_commit']==candidate['commit']
def git(*args,**kwargs):return subprocess.check_output(['git','-C',str(root),*args],text=True,**kwargs).strip()
assert git('rev-parse','HEAD')==candidate['commit'] and not git('status','--porcelain')
path='crates/sail-execution/src/owned_multipart.rs'
source=(root/path).read_text();start=source.index('pub fn execution_error(');end=source.index('\n#[cfg(test)]',start)
control=source[:start]+'''pub fn execution_error(error: MultipartError) -> DataFusionError {
    DataFusionError::External(Box::new(error))
}
'''+source[end:]
blob=git('hash-object','-w','--stdin',input=control)
fd,index=tempfile.mkstemp(prefix='sdp-execution-multipart-control-');os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',candidate['commit'],env=env)
 git('update-index','--cacheinfo','100644,'+blob+','+path,env=env)
 tree=git('write-tree',env=env)
 commit=git('commit-tree',tree,'-p',candidate['commit'],'-m','test control: omit multipart unknown-commit marker')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/failed-gates/execution-multipart-unknown-marker',commit)
subprocess.run(['git','-C',str(root),'checkout','--detach',commit],check=True)
command=['cargo','+1.98.1','test','-p','sail-execution','--lib','--locked','owned_multipart::tests::failed_completion_is_nonretryable_with_original_provider_cause_in_scope']
log=Path('/tmp/sail-sdp-execution-multipart-unknown-control.log')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
started=datetime.now(timezone.utc).isoformat()
with log.open('w') as output:r=subprocess.run(command,cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT)
assert git('rev-parse','HEAD')==commit and not git('status','--porcelain')
receipt={'candidate':candidate['commit'],'control':commit,'command':command,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'expected_exit':101,'actual_exit':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'scope':'Only mapper marker removal, unchanged regression test; expected failure'}
Path('/tmp/sail-sdp-execution-multipart-unknown-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert r.returncode==101 and 'assertion failed: !cause.is_retryable()' in log.read_text(),log.read_text()
subprocess.run(['git','-C',str(root),'checkout','--detach',candidate['commit']],check=True)
print('PASS expected unknown-commit control failure '+commit,flush=True)
