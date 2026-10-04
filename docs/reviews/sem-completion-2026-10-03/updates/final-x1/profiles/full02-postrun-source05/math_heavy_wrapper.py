import json,hashlib,os,subprocess,uuid,sys
from pathlib import Path
from datetime import datetime,timezone
b=Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003')
r=b/'X1-scale24-02-math-heavy-root01';r.mkdir(mode=0o700)
def pin(p):
 p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
closure=b/'X1-native-scale24-02-independent-closure01/closed/receipt.json'
v=json.loads(closure.read_text());assert v['outcome']=='passed_independent_twohost_case_closure' and v['immutable_closure'] and v['all_recorded_owned_processes_absent'] and v['locks_released'] and not v['errors']
memory=b/'X1-scale24-02-natural-memory-closure-root01/receipt.json'
assert json.loads(memory.read_text())['outcome']=='closed_natural_twohost_bounded_memory_observations_only'
source=b/'X1-scale24-02-root-postrun-source05/math.py'
expected=json.loads((source.parent/'receipt.json').read_text())['sources']['math']
assert pin(source)==expected
token=uuid.uuid4().hex;acquired=[];errors=[];code=1;child=None
locks=[Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/gate.lock'),Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/serial-queue.lock'),Path('/tmp/morrobay-sem-completion-heavy.lock')]
payloads={str(p):(json.dumps({'token':token,'pid':os.getpid(),'pgid':os.getpgrp(),'role':'original-scale24-independent-full-oracle','observed_utc':datetime.now(timezone.utc).isoformat()}) if p==locks[-1] else token) for p in locks}
try:
 for p in locks:
  p.mkdir(mode=0o700);acquired.append(p);(p/'owner.json').write_text(payloads[str(p)])
 (r/'launch.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'pgid':os.getpgrp(),'source':pin(source),'case_closure':pin(closure),'memory_closure':pin(memory),'token':token,'locks':[str(p) for p in locks]},indent=2)+'\n')
 with (r/'math.stdout').open('xb') as out,(r/'math.stderr').open('xb') as err:
  child=subprocess.Popen(['/tmp/sem-output-oracle-venv/bin/python','-I','-B',str(source)],stdin=subprocess.DEVNULL,stdout=out,stderr=err,env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','AWS_','MINIO_','PYTHON','DYLD_'))})
  (r/'orchestrator-launch.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'pid':child.pid,'pgid':os.getpgrp(),'argv':['/tmp/sem-output-oracle-venv/bin/python','-I','-B',str(source)]},indent=2)+'\n')
  code=child.wait()
 assert pin(source)==expected
except BaseException as error:
 errors.append(repr(error))
 if child is not None and child.poll() is None:
  try:child.wait(timeout=240)
  except BaseException as pending:errors.append('orchestrator still not closed: '+repr(pending))
finally:
 rows=subprocess.run(['/bin/ps','-axo','pid=,pgid='],capture_output=True,text=True,check=True).stdout.splitlines()
 active=set()
 inner=b/'X1-scale24-02-independent-math-root01/child-launch.json'
 if inner.exists():
  started=json.loads(inner.read_text());known={started['pid'],started['pgid']};active={int(x) for line in rows for x in line.split() if int(x) in known}
 journal_proven=(child is None or inner.exists())
 if not journal_proven:errors.append('oracle journal absent after orchestrator launch; locks retained pending independent closure')
 release_allowed=(child is None or child.poll() is not None) and not active and journal_proven
 if not release_allowed:errors.append('owned math process remains active; locks retained')
 for p in reversed(acquired) if release_allowed else []:
  try:
   assert (p/'owner.json').read_text()==payloads[str(p)]
   (p/'owner.json').unlink();p.rmdir()
  except BaseException as error:errors.append('owned lock release: '+repr(error))
 result={'observed_utc':datetime.now(timezone.utc).isoformat(),'outcome':'closed_actual_math_orchestration' if code==0 and not errors else 'failed_preserved_math_orchestration','returncode':code,'owned_locks_released':all(not p.exists() for p in acquired),'source_unchanged':pin(source)==expected,'errors':errors,'scope':'One native independent full oracle under owned local heavy locks after closed two-host engine and memory observers. This wrapper adds no mathematical verdict.'}
 (r/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result));sys.exit(0 if code==0 and not errors else 1)
