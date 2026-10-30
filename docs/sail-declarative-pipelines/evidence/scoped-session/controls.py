from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate='/Users/alexy/src/sail-sdp-gate';python=str(root/'.venv/bin/python');label='scoped-session-provider-qualified';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());source=root/'crates/sail-common-datafusion/src/session/scoped.rs';original=source.read_text()
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':python,'VIRTUAL_ENV':str(root/'.venv'),'PYTHONPATH':str(root/'.venv/lib/python3.12/site-packages')}
controls=[('scoped-session-runtime-provider-bypass',original.replace('        &self.runtime\n','        self.state.runtime_env()\n'),['real_provider_and_custom_planner_receive_overlay_and_exact_owner']),('scoped-session-builder-provider-rebuild',original.replace('        state.config_mut().set_extension(resources.clone());','''        state.config_mut().set_extension(resources.clone());
        let config = state.config().clone();
        let id = state.session_id().to_owned();
        let mut state = datafusion::execution::SessionStateBuilder::new_from_existing(state)
            .with_session_id(id).build();
        *state.config_mut() = config;'''),['preserves_native_prepared_plan_registry','preserves_config_sensitive_udf_without_rebinding'])]
for name,changed,tests in controls:
 assert changed!=original and source.read_text()==original
 try:
  source.write_text(changed)
  subprocess.run([python,'/tmp/sail-sdp-make-candidate.py',name,'test: isolate Session preservation control',*c['paths']],cwd=root,check=True)
 finally:source.write_text(original)
 ctrl=json.loads(Path('/tmp/sail-sdp-'+name+'-candidate.json').read_text());receipt={'commit':ctrl['commit'],'fixed_commit':c['commit'],'started_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
 for test in tests:
  cmd=['cargo','+1.98.1','test','-p','sail-common-datafusion','--lib','--locked',test,'--','--nocapture'];log=Path('/tmp/sail-sdp-'+name+'-'+test+'.log')
  with log.open('x')as out:result=subprocess.run(cmd,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
  receipt['checks'].append({'test':test,'command':cmd,'exit_code':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()});receipt['updated_at']=datetime.now(timezone.utc).isoformat();Path('/tmp/sail-sdp-'+name+'-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  assert result.returncode==101 and '0 passed; 1 failed;'in log.read_text(),log
 print('PASS unchanged negative control '+name,flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
subprocess.run([python,'/tmp/sail-sdp-package-release-stress.py',label,'','sail-common-datafusion'],check=True)
