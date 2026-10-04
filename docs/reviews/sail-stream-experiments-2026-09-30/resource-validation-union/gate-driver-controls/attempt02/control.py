import ast, hashlib, importlib.util, json, os, subprocess, sys, tempfile
from datetime import datetime,timezone
from pathlib import Path
p=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/run_gate.py')
ast.parse(p.read_text())
spec=importlib.util.spec_from_file_location('union_gate',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.GROUP_TERM_GRACE=.2;m.GROUP_KILL_GRACE=3
results=[];children=[];descendants=[]
out=Path(tempfile.mkdtemp(prefix='union-gate-cleanup-control-'))
receipt=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='RUNNING',script_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='Only stop_group controls; no source worktree or build. Test-local TERM/KILL grace .2/3seconds; production30/10seconds.',controls=results,cleanup=[])
def save():
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
save()
try:
 for name,code,finish in [('finished','pass',True),('active','import time;time.sleep(60)',False),('leader_exited_child_ignores_term', '''import os,signal,time
r,w=os.pipe()
pid=os.fork()
if pid==0:
 os.close(r);signal.signal(signal.SIGTERM,signal.SIG_IGN);os.write(w,b'1');os.close(w);time.sleep(60);os._exit(0)
os.close(w);os.read(r,1);os.close(r);print(pid,flush=True);os._exit(0)
''',True)]:
  child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  children.append(child)
  record=dict(case=name,pid=child.pid);results.append(record);save()
  if name.startswith('leader_'):
   descendant=int(child.stdout.readline());assert descendant>0;descendants.append(descendant);record['descendant']=descendant;save()
  if finish:child.wait(timeout=5)
  result=m.stop_group(child);record.update(result);save()
  assert result['leader_reaped'] and result['group_absent']
  if name.startswith('leader_'):assert 'SIGKILL' in result['signals']
 receipt['outcome']='PASS'
except BaseException as error:
 receipt.update(outcome='FAIL',error=repr(error))
finally:
 for child in children:
  try:
   child.poll()
   if child.returncode is None:child.kill()
   child.wait(timeout=5)
   receipt['cleanup'].append(dict(pid=child.pid,reaped=True,returncode=child.returncode))
  except BaseException as error:receipt['cleanup'].append(dict(pid=child.pid,error=repr(error)))
 for pid in descendants:
  try:os.kill(pid,9);receipt['cleanup'].append(dict(descendant=pid,kill_sent=True))
  except ProcessLookupError:receipt['cleanup'].append(dict(descendant=pid,absent=True))
  except BaseException as error:receipt['cleanup'].append(dict(descendant=pid,error=repr(error)))
 receipt['finished_utc']=datetime.now(timezone.utc).isoformat();save()
 (out/'control.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(dict(receipt=str(out/'receipt.json'),**receipt),indent=2))
print('AST_PASS',len(p.read_text().splitlines()),hashlib.sha256(p.read_bytes()).hexdigest())
assert receipt['outcome']=='PASS'
