from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib,os
p=Path('/tmp/sail-sdp-planning-state-registry-probe');p.mkdir(exist_ok=False)
c=json.loads(Path(str(p)+'-candidate.json').read_text());root='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
r={'commit':c['commit'],'base':c['base'],'started_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
for name,cmd in [('fmt',['cargo','+nightly','fmt','-p','sail-common-datafusion','--','--check']),('test',['cargo','+1.98.1','test','-p','sail-common-datafusion','--lib','--locked','planning_state_registry_probe','--','--nocapture'])]:
 with (p/(name+'.log')).open('x')as f:result=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT)
 r['checks'].append({'name':name,'command':cmd,'exit_code':result.returncode,'sha256':hashlib.sha256((p/(name+'.log')).read_bytes()).hexdigest()})
 r['finished_at']=datetime.now(timezone.utc).isoformat();(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
 assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
 assert result.returncode==0,(name,result.returncode)
print('PASS design-only prepared/UDF state preservation probe '+c['commit'])
