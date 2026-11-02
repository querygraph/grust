from pathlib import Path
from datetime import datetime,timezone
import os,json,hashlib,subprocess
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate='/Users/alexy/src/sail-sdp-gate';python=str(root/'.venv/bin/python');label='resolver-read-session';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());source=root/'crates/sail-plan/src/resolver/session.rs';original=source.read_text();needle='Some(session) => ProviderSession::Captured(session),';assert original.count(needle)==1
try:
 source.write_text(original.replace(needle,'Some(_) => ProviderSession::Legacy(Box::new(self.ctx.state())),') )
 subprocess.run([python,'/tmp/sail-sdp-make-candidate.py','resolver-read-session-bypass','test: isolate captured read factory Session routing',*c['paths']],cwd=root,check=True)
finally:source.write_text(original)
control=json.loads(Path('/tmp/sail-sdp-resolver-read-session-bypass-candidate.json').read_text());log=Path('/tmp/sail-sdp-resolver-read-session-bypass.log');command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::query::session_tests::factories','--','--nocapture'];started=datetime.now(timezone.utc).isoformat()
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':python,'VIRTUAL_ENV':str(root/'.venv'),'PYTHONPATH':str(root/'.venv/lib/python3.12/site-packages')}
with log.open('x')as out:result=subprocess.run(command,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
r={'commit':control['commit'],'fixed_commit':c['commit'],'command':command,'exit_code':result.returncode,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};Path('/tmp/sail-sdp-resolver-read-session-bypass-receipt.json').write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==101 and '1 passed; 3 failed;'in log.read_text() and log.read_text().count('session extension not found: task resource scope')==3,log
print('PASS unchanged read-factory bypass control '+control['commit'],flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
subprocess.run([python,'/tmp/sail-sdp-package-release-stress.py',label,'','sail-plan'],check=True)
subprocess.run([python,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-resolver-read-session-public'],check=True)
