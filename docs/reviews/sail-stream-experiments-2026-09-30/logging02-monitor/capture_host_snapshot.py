from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib
root=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/logging02-monitor');now=datetime.now(timezone.utc)
code=r'''
from datetime import datetime,timezone
from pathlib import Path
import subprocess,json,hashlib
p=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/logging02/host-before.json');data=p.read_bytes()
r={'started_utc':datetime.now(timezone.utc).isoformat(),'host_before_path':str(p),'host_before_sha256':hashlib.sha256(data).hexdigest(),'host_before_text':data.decode(),'snapshots':{}}
for name,command in [('date',['/bin/date','-u']),('physical_memory',['/usr/sbin/sysctl','hw.memsize']),('swap',['/usr/sbin/sysctl','vm.swapusage']),('vm_stat',['/usr/bin/vm_stat']),('processes',['/bin/ps','-axo','pid=,ppid=,rss=,comm='])]:
 q=subprocess.run(command,text=True,capture_output=True,timeout=10);r['snapshots'][name]={'command':command,'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
r['finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(r))
'''
r={'started_utc':now.isoformat(),'source':code,'scope':'Serialized host-only read; baseline bytes plus date/memory/PID/PPID/RSS/comm. No VM/Docker operation, process arguments/environment or signals.'}
try:
 p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=code,text=True,capture_output=True,timeout=45);r.update(returncode=p.returncode,stderr=p.stderr)
 if p.returncode:r['stdout']=p.stdout
 else:
  r['host']=json.loads(p.stdout);before=r['host'].pop('host_before_text').encode();assert hashlib.sha256(before).hexdigest()==r['host']['host_before_sha256']
  path=root/'host-before.json'
  if path.exists():assert path.read_bytes()==before
  else:path.write_bytes(before)
except subprocess.TimeoutExpired as e:r.update(error=repr(e),stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
r['finished_utc']=datetime.now(timezone.utc).isoformat();path=root/('host-control-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json');path.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'output':str(path),'returncode':r.get('returncode'),'error':r.get('error'),'swap':r.get('host',{}).get('snapshots',{}).get('swap'),'baseline_sha256':r.get('host',{}).get('host_before_sha256')},indent=2))
