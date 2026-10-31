from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';c=json.loads(Path('/tmp/sail-sdp-constant-context-arithmetic-candidate.json').read_text());base=c['commit']
r=json.loads(Path('/tmp/sail-sdp-constant-context-arithmetic-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==base
baseline=json.loads(Path('/tmp/sail-sdp-constant-lowering-baseline/receipt.json').read_text());assert baseline['before']==baseline['after'] and baseline['before']['sail_commit']==c['base'] and baseline['server_exit_code']==baseline['probe_exit_code']==0 and baseline['remaining_listener_pids']==[]
def git(*a,**kw):return subprocess.check_output(['git','-C',ROOT,*a],text=True,**kw).strip()
assert subprocess.check_output(['git','-C',GATE,'rev-parse','HEAD'],text=True).strip()==c['base']
assert not subprocess.check_output(['git','-C',GATE,'status','--porcelain'],text=True).strip()
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
path='crates/sail-plan/src/function/scalar/math.rs';test='crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs';s=git('show',base+':'+path)
old='!function_context.constant_context && is_zero_literal(&divisor)';assert s.count(old)==3;s=s.replace(old,'!function_context.require_foldable && is_zero_literal(&divisor)')
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: restore eager scalar constant arithmetic')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/constant-context-arithmetic',control)
assert git('diff','--name-only',base,control)==path and git('rev-parse',base+':'+test)==git('rev-parse',control+':'+test)
subprocess.run(['git','-C',GATE,'checkout','--detach',control],check=True)
cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::identifier::arithmetic_tests::']
log=Path('/tmp/sail-sdp-constant-lowering-control.log');runenv={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':ROOT+'/.venv/bin/python'}
with log.open('w') as out:result=subprocess.run(cmd,cwd=GATE,env=runenv,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-constant-lowering-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'base':base,'control':control,'exit_code':result.returncode,'command':cmd,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'test_blob':git('rev-parse',base+':'+test)},indent=2)+'\n')
assert result.returncode==101 and '0 passed; 1 failed;' in log.read_text(),log.read_text()[-3000:]
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
print('PASS unchanged arithmetic control:0 pass/1 fail',flush=True)
