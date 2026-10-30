from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,os
p=Path('/tmp/sail-sdp-fable-lower-json-correction-review');root='/Users/alexy/src/sail-sdp-gate';r=json.loads((p/'receipt.json').read_text());commit=r['commit']
assert subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip()==commit and not subprocess.check_output(['git','-C',root,'status','--porcelain'])
cmd=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','pipelines::streaming','--','--nocapture'];out={'commit':commit,'command':cmd,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Offered pure streaming components plus the three independent lowerer fixtures; no adapter/effect integration claim'}
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
with (p/'streaming.log').open('x')as f:result=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT)
out.update(exit_code=result.returncode,finished_at=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256((p/'streaming.log').read_bytes()).hexdigest());(p/'streaming-receipt.json').write_text(json.dumps(out,indent=2)+'\n')
assert result.returncode==0 and '44 passed; 0 failed;'in(p/'streaming.log').read_text(),p/'streaming.log'
assert subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip()==commit and not subprocess.check_output(['git','-C',root,'status','--porcelain'])
print('PASS 44 independent pure streaming component/regression tests '+commit)
