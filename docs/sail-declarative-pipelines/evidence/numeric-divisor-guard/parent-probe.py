from pathlib import Path
import json,os,subprocess,hashlib
from datetime import datetime,timezone
ROOT='/Users/alexy/src/sail-pipelines-proposal';GATE='/Users/alexy/src/sail-sdp-gate';PYTHON=ROOT+'/.venv/bin/python'
base='5a1142bcd90b97385314610f1342e1a9a4879690';candidate='b857dabb74da0484b781c096f9a9cd6a78daaa5c'
def git(*args):return subprocess.check_output(['git','-C',GATE,*args],text=True).strip()
assert git('rev-parse','HEAD')==candidate and not git('status','--porcelain')
subprocess.run(['git','-C',GATE,'checkout','--detach',base],check=True)
command=['cargo','+1.98.1','build','-p','sail-cli','--locked']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_TARGET_DIR':GATE+'/target','PYO3_PYTHON':PYTHON,'VIRTUAL_ENV':ROOT+'/.venv','PYTHONPATH':ROOT+'/.venv/lib/python3.12/site-packages','PYTHONDONTWRITEBYTECODE':'1'}
log=Path('/tmp/sail-sdp-numeric-divisor-parent-build.log')
with log.open('x') as output:r=subprocess.run(command,cwd=GATE,env=env,stdout=output,stderr=subprocess.STDOUT)
receipt={'sail_commit':base,'command':command,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'scope':'Exact-source clean detached parent CLI build for22 decimal/CASE/string probes only; no new parent public-suite verdict','recorded_at':datetime.now(timezone.utc).isoformat()}
assert git('rev-parse','HEAD')==base and not git('status','--porcelain')
receipt['cli_sha256']=hashlib.sha256(Path(GATE+'/target/debug/sail').read_bytes()).hexdigest()
p=Path('/tmp/sail-sdp-numeric-divisor-parent-build.json');p.write_text(json.dumps(receipt,indent=2)+'\n');assert r.returncode==0
subprocess.run([PYTHON,'/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/deferred-arithmetic/run-probe.py','/tmp/sail-sdp-numeric-divisor-additional-parent',base,str(p),'identifier','/tmp/sail-sdp-numeric-divisor-additional-reference-v2.py'],check=True)
subprocess.run(['git','-C',GATE,'checkout','--detach',candidate],check=True)
print('PASS parent CLI22 recorded; gate restored candidate; CLI remains parent binary',flush=True)
