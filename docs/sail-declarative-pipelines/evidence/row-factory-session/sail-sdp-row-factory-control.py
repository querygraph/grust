from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,tempfile
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='row-factory-session'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
def git(*args,**kwargs):return subprocess.check_output(['git','-C',repo,*args],text=True,**kwargs).strip()
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
positive=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert positive['outcome']=='passed'
opt=json.loads(Path('/tmp/sail-sdp-'+label+'-sail-plan-release/receipt.json').read_text());assert opt['outcome']=='passed'
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',c['commit'],env=env)
 for path in c['paths']:
  if '/command/' in path:
   blob=git('rev-parse',c['base']+':'+path);git('update-index','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',c['commit'],'-m','Bypass selected lake metadata Session with identical regression fixtures')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/row-factory-session-bypass',commit)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
ctl={'base':c['commit'],'commit':commit,'paths':c['paths']};Path('/tmp/sail-sdp-row-factory-session-bypass-candidate.json').write_text(json.dumps(ctl,indent=2)+'\n')
command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::query::session_tests::row_factories']
env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'}
log=Path('/tmp/sail-sdp-row-factory-session-bypass.log')
with log.open('w') as output: result=subprocess.run(command,cwd=gate,env=env,stdout=output,stderr=subprocess.STDOUT)
receipt={'commit':commit,'base':c['commit'],'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'recorded_at':datetime.now(timezone.utc).isoformat()}
Path('/tmp/sail-sdp-row-factory-session-bypass-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert result.returncode==101 and 'test result: FAILED. 4 passed; 4 failed;' in log.read_text(),log.read_text()[-8000:]
assert log.read_text().count('session extension not found: task resource scope')>=4,log.read_text()[-8000:]
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
print('PASS unchanged lake metadata bypass: four scoped failures, four legacy passes')
