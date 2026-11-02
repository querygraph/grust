from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess
p=Path('/tmp/sail-sdp-coordination-reader-gate');p.mkdir()
root=Path('/Users/alexy/src/grust-sdp-review-gate')
c=json.loads(Path('/tmp/sail-sdp-evidence-candidate.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
r={'commit':c['commit'],'recorded_at':datetime.now(timezone.utc).isoformat(),'scope':'Temporary-log unit tests; optimized Python concurrency run with one owned busy process per logical CPU','checks':[]}
def save():(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
for name,cmd in [('docs',['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','/tmp/sail-sdp-evidence-gate.py']),('tests',['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','-B','scripts/sdp-coordination-append-tests.py','-v'])]:
 with (p/(name+'.log')).open('w') as log:ret=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
 r['checks'].append({'name':name,'command':cmd,'exit_code':ret.returncode,'log_sha256':hashlib.sha256((p/(name+'.log')).read_bytes()).hexdigest()});save();assert ret.returncode==0,(p/(name+'.log')).read_text()
workers=[]
try:
 with open(os.devnull,'wb') as sink:
  for _ in range(os.cpu_count() or 1):workers.append(subprocess.Popen(['/usr/bin/yes'],stdout=sink,stderr=sink))
  assert all(w.poll() is None for w in workers)
  r['load_pids']=[w.pid for w in workers];r['logical_cpus']=os.cpu_count();save()
  cmd=['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','-B','-O','scripts/sdp-coordination-append-tests.py','-v']
  with (p/'optimized.log').open('w') as log:ret=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=60)
  r['checks'].append({'name':'optimized_load','command':cmd,'exit_code':ret.returncode,'log_sha256':hashlib.sha256((p/'optimized.log').read_bytes()).hexdigest()})
finally:
 for w in workers:
  if w.poll() is None:w.terminate()
 for w in workers:w.wait(timeout=10)
 r['load_exit_codes']=[w.returncode for w in workers];save()
assert ret.returncode==0,(p/'optimized.log').read_text()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
r['outcome']='passed';r['completed_at']=datetime.now(timezone.utc).isoformat();save()
print((p/'tests.log').read_text());print((p/'optimized.log').read_text())
print('PASS coordination protocol '+c['commit'])
