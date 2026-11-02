from pathlib import Path
import json,hashlib,subprocess,os
from datetime import datetime,timezone
G='/Users/alexy/src/sail-sdp-gate';R='/Users/alexy/src/sail-pipelines-proposal';c=json.load(open('/tmp/sail-sdp-decimal-config-candidate.json'));assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==c['commit']
cmd=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','session_manager::orc_options_tests::write_defaults_follow_creation_set_unset_and_preserve_snapshots','--','--nocapture']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'};log=Path('/tmp/sail-sdp-decimal-config-env-control.log')
with log.open('x') as out:p=subprocess.run(cmd,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-decimal-config-env-control.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'sail_commit':c['commit'],'command':cmd,'overrides':{k:env[k] for k in ['PYO3_PYTHON','PYTHONPATH','VIRTUAL_ENV']},'exit_code':p.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
print(log.read_text()[-1800:]);assert p.returncode==0
