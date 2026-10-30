from pathlib import Path
from datetime import datetime,timezone
import os,json,hashlib,subprocess
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate='/Users/alexy/src/sail-sdp-gate';python=str(root/'.venv/bin/python');label='resolver-query-session-registry';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());source=root/'crates/sail-plan/src/resolver/session.rs';original=source.read_text()
needle='''                let physical = session.create_physical_plan(&plan).await?;
                Ok(collect(physical, session.task_ctx()).await?)'''
replacement='''                let _ = session;
                Ok(self.ctx.execute_logical_plan(plan).await?.collect().await?)'''
assert original.count(needle)==1
try:
 source.write_text(original.replace(needle,replacement))
 subprocess.run([python,'/tmp/sail-sdp-make-candidate.py','resolver-helper-session-bypass','test: isolate helper query Session bypass',*c['paths']],cwd=root,check=True)
finally:source.write_text(original)
control=json.loads(Path('/tmp/sail-sdp-resolver-helper-session-bypass-candidate.json').read_text());log=Path('/tmp/sail-sdp-resolver-helper-session-bypass.log');cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','resolver::query::session_tests','--','--nocapture'];started=datetime.now(timezone.utc).isoformat()
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':python,'VIRTUAL_ENV':str(root/'.venv'),'PYTHONPATH':str(root/'.venv/lib/python3.12/site-packages')}
with log.open('x')as f:result=subprocess.run(cmd,cwd=gate,env=env,stdout=f,stderr=subprocess.STDOUT)
r={'commit':control['commit'],'fixed_commit':c['commit'],'command':cmd,'exit_code':result.returncode,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};Path('/tmp/sail-sdp-resolver-helper-session-bypass-receipt.json').write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==101 and '1 passed; 4 failed;'in log.read_text(),log
assert 'session extension not found: TaskResourceScope'in log.read_text(),log
print('PASS unchanged four-helper bypass control '+control['commit'],flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
subprocess.run([python,'/tmp/sail-sdp-package-release-stress.py',label,'','sail-plan'],check=True)
subprocess.run([python,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-resolver-query-session-public'],check=True)
