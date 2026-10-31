from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
base=json.loads(Path('/tmp/sail-sdp-sdp-computed-binding-v2-candidate.json').read_text())['commit']
assert json.loads(Path('/tmp/sail-sdp-sdp-computed-binding-v2-gate.json').read_text())['outcome']=='passed'
def git(*a,**kw):return subprocess.check_output(['git','-C',str(root),*a],text=True,**kw).strip()
path='crates/sail-spark-connect/src/pipelines/analysis.rs';test='crates/sail-spark-connect/src/pipelines/config/runtime_tests.rs'
s=git('show',base+':'+path)
old="fn resolve_late_bound(&self, _: &[String]) -> PlanResult<Option<LogicalPlan>> {\n        Ok(None)\n    }"
new="fn resolve_late_bound(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {\n        self.resolve(name)\n    }"
assert s.count(old)==1;s=s.replace(old,new)
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: bind computed pipeline targets through the early graph scope')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/sdp-computed-target',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
assert subprocess.check_output(['git','-C',str(gate),'rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C',str(gate),'status','--porcelain'],text=True).strip()
subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
cmd=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','computed_target_does_not_bind_or_inherit_the_graph_view']
log=Path('/tmp/sail-sdp-sdp-computed-target-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
with log.open('w') as out:result=subprocess.run(cmd,cwd=gate,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-sdp-computed-target-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-2000:]
subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
print('PASS unchanged SDP control: computed graph lookup fails the runtime regression',flush=True)
