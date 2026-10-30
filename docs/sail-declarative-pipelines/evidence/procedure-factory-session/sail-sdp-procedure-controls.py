from pathlib import Path
from datetime import datetime,timezone
import os,json,hashlib,subprocess,tempfile
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='procedure-factory-session';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());path='crates/sail-plan/src/resolver/command/procedure.rs'
def git(*a,**kw):return subprocess.check_output(['git','-C',repo,*a],text=True,**kw).strip()
assert json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())['outcome']=='passed';assert json.loads(Path('/tmp/sail-sdp-'+label+'-sail-plan-release/receipt.json').read_text())['outcome']=='passed'
for kind,expected in [('factory',(2,2)),('metadata',(3,1))]:
 original=git('show',c['commit']+':'+path)
 if kind=='factory':
  assert original.count('let session = self.provider_session();')==1;changed=original.replace('let session = self.provider_session();','let session = self.ctx.state();').replace('.plan_procedure(session.as_session(),','.plan_procedure(&session,')
 else:
  needle='.infer_metadata(self.provider_session().as_session(), *info.clone())';assert original.count(needle)==1;changed=original.replace(needle,'.infer_metadata(&self.ctx.state(), *info.clone())')
 fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',c['commit'],env=env);blob=git('hash-object','-w','--stdin',input=changed+'\n');git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',c['commit'],'-m','Bypass selected procedure '+kind+' Session with unchanged tests')
 finally:Path(index).unlink(missing_ok=True)
 packet='procedure-'+kind+'-bypass';git('update-ref','refs/sdp/evidence/'+packet,commit);subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
 Path('/tmp/sail-sdp-'+packet+'-candidate.json').write_text(json.dumps({'base':c['commit'],'commit':commit,'paths':[path],'kind':kind},indent=2)+'\n')
 log=Path('/tmp/sail-sdp-'+packet+'.log');command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::query::session_tests::procedures'];env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
 with log.open('w') as output:result=subprocess.run(command,cwd=gate,env=env,stdout=output,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-'+packet+'-receipt.json').write_text(json.dumps({'commit':commit,'base':c['commit'],'command':command,'exit_code':result.returncode,'expected_passed':expected[0],'expected_failed':expected[1],'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'recorded_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
 assert result.returncode==101 and f'test result: FAILED. {expected[0]} passed; {expected[1]} failed;' in log.read_text(),log.read_text()[-5000:]
 print('PASS unchanged procedure '+kind+' bypass: '+str(expected),flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
