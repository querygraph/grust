from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';base=subprocess.check_output(['git','-C',repo,'rev-parse','d1f2fd565'],text=True).strip();old='8907014d7c51ca0ffc8fc73f2ef5e526552287e0';path='crates/sail-spark-connect/src/pipelines/streaming/binding_tests.rs'
def git(*a,**kw):return subprocess.check_output(['git','-C',repo,*a],text=True,**kw).strip()
s=git('show',base+':'+path)+'\n';original=git('show',old+':'+path)+'\n';fixture=original[original.index('fn inline_table_function'):];s+='\nmod codex_guard_replay {\nuse super::*;\n'+fixture+'}\n'
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=s);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',base,'-m','Replay unchanged dynamic inline UDTF guard fixtures against correction')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/dynamic-udtf-guard-correction-replay',commit)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
c={'base':base,'commit':commit,'fixture_source':old,'paths':[path],'fixture_sha256':hashlib.sha256(fixture.encode()).hexdigest()};Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay-candidate.json').write_text(json.dumps(c,indent=2)+'\n');Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay.patch').write_text(git('diff',base,commit)+'\n')
command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','codex_guard_replay'];env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'};log=Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay.log')
with log.open('w') as output:result=subprocess.run(command,cwd=gate,env=env,stdout=output,stderr=subprocess.STDOUT)
receipt={**c,'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'recorded_at':datetime.now(timezone.utc).isoformat()};Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert git('rev-parse','HEAD')=='0e23b2613f809604ec72757b56e4fa2f9b922b2a'
assert result.returncode==0 and 'test result: ok. 2 passed; 0 failed;' in log.read_text(),log.read_text()[-6000:]
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
print('PASS unchanged UDTF guard replay',commit,'2pass/0fail')
