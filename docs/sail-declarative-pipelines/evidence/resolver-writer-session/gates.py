from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate='/Users/alexy/src/sail-sdp-gate';python=str(root/'.venv/bin/python');label='resolver-write-session-options';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());source=root/'crates/sail-plan/src/resolver/command/write.rs';original=source.read_text()
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':python,'VIRTUAL_ENV':str(root/'.venv'),'PYTHONPATH':str(root/'.venv/lib/python3.12/site-packages')}
controls=[('writer-session-bypass','.create_writer(self.provider_session().as_session(), sink_info)','.create_writer(&self.ctx.state(), sink_info)','resolver::query::session_tests::writers','1 passed; 2 failed;',2),('writer-schema-session-bypass','.infer_schema(self.provider_session().as_session(), info)','.infer_schema(&self.ctx.state(), info)','empty_catalog_schema_and_writer_share_selected_session','0 passed; 1 failed;',1)]
for name,needle,replacement,pattern,summary,count in controls:
 assert original.count(needle)==1 and source.read_text()==original
 try:
  source.write_text(original.replace(needle,replacement));subprocess.run([python,'/tmp/sail-sdp-make-candidate.py',name,'test: isolate writer planning Session propagation',*c['paths']],cwd=root,check=True)
 finally:source.write_text(original)
 ctrl=json.loads(Path('/tmp/sail-sdp-'+name+'-candidate.json').read_text());log=Path('/tmp/sail-sdp-'+name+'.log');cmd=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked',pattern,'--','--nocapture'];started=datetime.now(timezone.utc).isoformat()
 with log.open('x')as out:result=subprocess.run(cmd,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
 r={'commit':ctrl['commit'],'fixed_commit':c['commit'],'command':cmd,'exit_code':result.returncode,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};Path('/tmp/sail-sdp-'+name+'-receipt.json').write_text(json.dumps(r,indent=2)+'\n')
 assert result.returncode==101 and summary in log.read_text() and log.read_text().count('session extension not found: task resource scope')==count,log
 print('PASS unchanged negative control '+name,flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
subprocess.run([python,'/tmp/sail-sdp-package-release-stress.py',label,'','sail-plan'],check=True)
subprocess.run([python,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-resolver-write-session-public'],check=True)
