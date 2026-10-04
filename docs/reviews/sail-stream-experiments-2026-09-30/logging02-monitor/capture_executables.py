"""One supplemental read-only executable/start-tick identity check."""
from datetime import datetime,timezone
from pathlib import Path
import json,subprocess,hashlib
root=Path(__file__).parent
vm=r'''
from pathlib import Path
import hashlib,json,time
cid='277559b777e04a8bdda5f0cb8931480269de472f0fbf2e2125375496118fab16'
expected='40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497'
def ticks(p):return int(p.read_text().rsplit(')',1)[1].split()[19])
record={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'monotonic_started':time.monotonic(),'processes':[]}
for pid,start in [(183665,14376571),(183782,14376781),(183784,14376782)]:
 r={'host_pid':pid,'expected_start_ticks':start};p=Path('/proc')/str(pid)
 try:
  r['start_ticks_before']=ticks(p/'stat');r['cgroup']=(p/'cgroup').read_text();assert cid in r['cgroup'];assert r['start_ticks_before']==start
  r['executable_target']=str((p/'exe').readlink())
  with (p/'exe').open('rb') as f:r['executable_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
  r['start_ticks_after']=ticks(p/'stat');assert r['start_ticks_after']==start
  r['matches_runtime289']=r['executable_sha256']==expected
 except Exception as e:r['error']=repr(e)
 record['processes'].append(r)
# Inspect only an initial bounded region for worker spawn identities.
p=Path('/var/lib/docker/volumes/sail-extension-targets/_data/sail-stream-experiments-20260930/logging02/cells/stream-log02-r1-scale24-pecan-sssp-delta_star/server.log')
try:
 with p.open('rb') as f:data=f.read(65536)
 record['worker_startup_excerpt']=[line.decode(errors='replace') for line in data.splitlines() if b'worker' in line.lower() and (b'pid' in line.lower() or b'start' in line.lower() or b'launch' in line.lower())][:20]
 record['startup_scan_bytes']=len(data)
except OSError as e:record['startup_error']=repr(e)
record['monotonic_finished']=time.monotonic();print(json.dumps(record))
'''
remote="import subprocess,json,os\nos.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')\nr=subprocess.run(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-c',"+repr(vm)+"],capture_output=True,text=True,timeout=45)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))\n"
now=datetime.now(timezone.utc);out=root/('executable-identity-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=remote,text=True,capture_output=True,timeout=60)
r={'started_utc':now.isoformat(),'finished_utc':datetime.now(timezone.utc).isoformat(),'returncode':p.returncode,'stderr':p.stderr,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Read-only proc executable hash for three previously mapped Sail processes; no argv/environment read.'}
if p.returncode:r['stdout']=p.stdout
else:
 r['capture']=json.loads(p.stdout)
 if r['capture']['returncode']==0:r['identity']=json.loads(r['capture'].pop('stdout'))
with out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps(r,indent=2))
