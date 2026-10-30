from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
root='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';commit='41f09ec470aa0415d23f5ecd0e0acdf792fb9987';p=Path('/tmp/sail-sdp-fable-binding-correction-review');p.mkdir(exist_ok=False)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
def state():
 head=subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip();assert head==commit and not subprocess.check_output(['git','-C',gate,'status','--porcelain']);return head
r={'commit':commit,'before':state(),'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Independent replay of two prior validator counterexamples; no provider/RPC/whole-suite claim'}
cmd=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','codex_review_unbound_','--','--nocapture'];r['command']=cmd;(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':root+'/.venv/bin/python','VIRTUAL_ENV':root+'/.venv','PYTHONPATH':root+'/.venv/lib/python3.12/site-packages'}
with (p/'test.log').open('x')as out:result=subprocess.run(cmd,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
r.update(exit_code=result.returncode,after=state(),finished_at=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256((p/'test.log').read_bytes()).hexdigest());(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==0 and '2 passed; 0 failed;'in(p/'test.log').read_text()
for name in ['codex_review_unbound_scalar_subquery_must_be_refused_before_resolution','codex_review_unbound_exists_predicate_must_be_refused_before_resolution']:assert '::'+name+' ... ok'in(p/'test.log').read_text()
print('PASS independent binding correction replay '+commit,flush=True)
