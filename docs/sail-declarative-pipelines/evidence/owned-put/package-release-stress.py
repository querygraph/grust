from datetime import datetime, timezone
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys

label,pattern,package=sys.argv[1:]
root=Path('/Users/alexy/src/sail-sdp-gate')
packet=Path('/tmp/sail-sdp-'+label+'-'+package+'-release')
packet.mkdir()
candidate=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
def head():return subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert head()==candidate['commit']
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'])
assert shutil.disk_usage(root).free>100*1024**3
env={**os.environ,'CARGO_PROFILE_RELEASE_DEBUG':'0','CARGO_PROFILE_RELEASE_LTO':'off','CARGO_PROFILE_RELEASE_CODEGEN_UNITS':'16','CARGO_PROFILE_RELEASE_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','CARGO_BUILD_JOBS':'4','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
command=['cargo','+1.98.1','test','--release','-p',package,'--lib','--locked','--no-run','--message-format=json']
receipt={'commit':candidate['commit'],'started_at':datetime.now(timezone.utc).isoformat(),'command':command,'environment':{k:v for k,v in env.items() if k.startswith('CARGO_') or k in ('PYO3_PYTHON','VIRTUAL_ENV','PYTHONPATH')},'scope':'Optimized library test binary with one busy process per logical CPU; no performance claim'}
def save():
 receipt['updated_at']=datetime.now(timezone.utc).isoformat()
 (packet/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
save()
with (packet/'build.jsonl').open('w') as out,(packet/'build.log').open('w') as err:
 result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=err)
receipt['build_exit']=result.returncode
save()
if result.returncode:raise SystemExit(result.returncode)
artifacts=[json.loads(line) for line in (packet/'build.jsonl').read_text().splitlines()]
executables=[a['executable'] for a in artifacts if a.get('reason')=='compiler-artifact' and a.get('executable') and a['target']['name']==package.replace('-', '_')]
assert len(executables)==1,executables
binary=Path(executables[0])
receipt['binary']=str(binary)
receipt['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
workers=[]
try:
 with open(os.devnull,'wb') as sink:
  for _ in range(os.cpu_count() or 1):
   workers.append(subprocess.Popen(['/usr/bin/yes'],stdout=sink,stderr=sink))
  assert all(worker.poll() is None for worker in workers)
  receipt['load_pids']=[worker.pid for worker in workers]
  receipt['logical_cpus']=os.cpu_count()
  receipt['test_command']=[str(binary),pattern,'--test-threads=1']
  save()
  with (packet/'test.log').open('w') as log:
   result=subprocess.run(receipt['test_command'],cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=120)
  receipt['test_exit']=result.returncode
finally:
 for worker in workers:
  if worker.poll() is None:worker.terminate()
 for worker in workers:worker.wait(timeout=10)
 receipt['load_worker_exit_codes']=[worker.returncode for worker in workers]
 save()
assert head()==candidate['commit']
assert result.returncode==0,(packet/'test.log').read_text()
assert '0 passed;' not in (packet/'test.log').read_text()
receipt['outcome']='passed'
receipt['finished_at']=datetime.now(timezone.utc).isoformat()
save()
print((packet/'test.log').read_text())
print('PASS optimized stress '+candidate['commit'])
