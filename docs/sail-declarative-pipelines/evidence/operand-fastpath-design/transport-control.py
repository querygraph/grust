from pathlib import Path
import subprocess,tempfile,os,hashlib,json
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';restore='4070e895b69338eb19f22643f0e40815da89ff34'
r=json.loads(Path('/tmp/sail-sdp-raw-replay-probe-v2.json').read_text());base=r['probe'];path=r['path']
def git(*args,**kw):return subprocess.check_output(['git','-C',ROOT,*args],text=True,**kw).strip()
s=git('show',base+':'+path);test_start=s.index('#[test]\nfn raw_replay_error_policy_matrix_probe');test_bytes=s[test_start:];start=s.index('fn native_data_error_policy_probe(');end=s.index('\n#[derive(Debug)]\nstruct OpaquePolicyEnvelope',start)
s=s[:start]+'''fn native_data_error_policy_probe(error: &(dyn std::error::Error+'static))->bool {
    use sail_common_datafusion::error::CommonErrorCause;
    matches!(CommonErrorCause::new::<ReplayNoPython>(error),CommonErrorCause::Execution(_)|CommonErrorCause::Structured(_)|CommonErrorCause::ArrowCast(_)|CommonErrorCause::ArrowParse(_)|CommonErrorCause::ArrowCompute(_)|CommonErrorCause::ArrowDivideByZero(_)|CommonErrorCause::ArrowArithmeticOverflow(_)|CommonErrorCause::InvalidArgument(_))
}
'''+s[end:]
assert s[s.index('#[test]\nfn raw_replay_error_policy_matrix_probe'):]==test_bytes
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Counterfactual probe: use lossy transport errors for arithmetic replay')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/raw-replay-transport-control',control)
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==restore
assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-function','--lib','--locked','raw_replay_error_policy_matrix_probe','--','--nocapture'];log=Path('/tmp/sail-sdp-raw-replay-transport-control.log')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':ROOT+'/.venv/bin/python','VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages'}
with log.open('x') as out:result=subprocess.run(command,cwd=GATE,env=env,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-raw-replay-transport-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base_probe':base,'control':control,'production_base':restore,'path':path,'test_section_sha256':hashlib.sha256(test_bytes.encode()).hexdigest(),'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'scope':'Counterfactual test-only prototype policy; no production change or production-control claim'},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',restore],check=True)
print('PASS raw policy counterfactual0/1; resource error wrongly admitted by transport category',flush=True)
