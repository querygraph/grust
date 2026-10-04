"""Bounded read-only logging02 observation; outputs only on the local host."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REMOTE = r'''
import hashlib,importlib.util,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
p=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/capture_process_identity.py')
request=json.loads(sys.stdin.read())
assert hashlib.sha256(p.read_bytes()).hexdigest()==request['reader_sha256']
spec=importlib.util.spec_from_file_location('identity_reader',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')
docker=['/usr/local/bin/docker','--context','colima-sail-gate']
record={'started_utc':datetime.now(timezone.utc).isoformat(),'container':'sail-stream-log02-1'}
inspection=m.run(docker+['inspect','--format','{{json .Id}} {{json .State}}','sail-stream-log02-1'])
record['inspection']=inspection
if inspection['returncode']==0:
 cid,state=inspection['stdout'].strip().split(' ',1);cid=json.loads(cid);state=json.loads(state)
 record['container_id']=cid;record['state']=state
 assert cid==request['container_id']
 if state['Running']:
  top=m.run(docker+['top',cid,'-eo','pid,ppid,comm']);record['top']=top
  assert top['returncode']==0
  identity={'container_id':cid,'init_host_pid':state['Pid'],'host_pids':([r['host_pid'] for r in m.parse_top(top['stdout'])] if request['capture_mapping'] else [])}
  volume=m.run(docker+['volume','inspect','--format','{{.Mountpoint}}','sail-extension-targets'])
  record['volume_inspection']=volume;assert volume['returncode']==0
  options={'identity':identity,'root':volume['stdout'].strip(),'previous_offset':request.get('previous_offset',0)}
  reader=m.VM_READER+'\n'+request['vm_observer']
  capture=m.run(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-c',reader,json.dumps(identity),json.dumps(options)])
  capture['command'][-3]='<pinned identity reader plus retained VM observer>'
  record['capture']=capture
  if capture['returncode']==0:
   blocks=[json.loads(line) for line in capture.pop('stdout').splitlines() if line.strip()]
   record['mapping'],record['observation']=blocks
record['finished_utc']=datetime.now(timezone.utc).isoformat()
print(json.dumps(record))
'''

VM_OBSERVER = r'''
import os,re
options=json.loads(sys.argv[2])
root=Path(options['root'])/'sail-stream-experiments-20260930/logging02/cells/stream-log02-r1-scale24-pecan-sssp-delta_star'
result={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'uptime':Path('/proc/uptime').read_text().strip(),'monotonic':time.monotonic(),'cpu_stat':Path('/proc/stat').read_text().splitlines()[0]}
init=options['identity']['init_host_pid'];cgtext=(Path('/proc')/str(init)/'cgroup').read_text();assert options['identity']['container_id'] in cgtext
cgpath=cgtext.split('::',1)[1].strip();cg=Path('/sys/fs/cgroup')/cgpath.lstrip('/')
result['cgroup_path']=cgpath;result['cgroup']={}
for name in ['memory.current','memory.peak','memory.max','memory.events','memory.stat','cpu.stat','cpuset.cpus.effective','io.stat']:
 p=cg/name
 try:result['cgroup'][name]=p.read_text()
 except OSError as e:result['cgroup'][name]={'error':repr(e)}
result['files']={}
for name,limit in [('memory-samples.jsonl',16384),('server.log',32768),('receipt.json',65536),('server-settings.json',16384)]:
 p=root/name
 if not p.exists():result['files'][name]={'exists':False};continue
 st=p.stat();offset=max(0,st.st_size-limit)
 with p.open('rb') as f:f.seek(offset);data=f.read(limit)
 result['files'][name]={'exists':True,'bytes_at_start':st.st_size,'mtime_ns':st.st_mtime_ns,'offset':offset,'tail_utf8':data.decode(errors='replace')}
 if name=='server.log':
  previous=min(options['previous_offset'],st.st_size);end=st.st_size;windows=[(previous,min(end,previous+2*1024**2))]
  if end-windows[0][1]>0:windows.append((max(windows[0][1],end-2*1024**2),end))
  errors=[]
  with p.open('rb') as f:
   for start,stop in windows:
    f.seek(start);chunk=f.read(stop-start)
    pos=start
    for line in chunk.splitlines(keepends=True):
     if re.search(rb'(?i)(?<![a-z])(?:ERROR|panic|panicked|OutOfMemory|failed|stream_error)(?![a-z])',line):
      if len(errors)<20:errors.append({'offset':pos,'line_utf8':line[:4096].decode(errors='replace'),'truncated':len(line)>4096})
     pos+=len(line)
  result['error_scan']={'windows':windows,'gap_bytes':max(0,end-previous-sum(b-a for a,b in windows)),'matches':errors,'next_offset':end,'scope':'First matches within bounded scanned windows only; full server log remains authoritative.'}
result['volume_free_bytes']=__import__('shutil').disk_usage(options['root']).free
print(json.dumps(result))
'''


def main():
    initial=json.loads((ROOT/'process-identity-01.json').read_text())
    previous=0
    last_mapping=datetime.fromisoformat(initial['started_utc'])
    for p in sorted(ROOT.glob('observation-*.json')):
        data=json.loads(p.read_text())
        previous=max(previous,data.get('observation',{}).get('error_scan',{}).get('next_offset',0))
        if data.get('mapping',{}).get('processes'):
            last_mapping=max(last_mapping,datetime.fromisoformat(data['started_utc']))
    reader=ROOT.parent/'capture_process_identity.py'
    request={'reader_sha256':hashlib.sha256(reader.read_bytes()).hexdigest(),
             'container_id':initial['identity']['container_id'],
             'previous_offset':previous,'vm_observer':VM_OBSERVER,
             'capture_mapping':(datetime.now(timezone.utc)-last_mapping).total_seconds()>=300}
    code=REMOTE.replace('request=json.loads(sys.stdin.read())', 'request=json.loads('+repr(json.dumps(request))+')')
    now=datetime.now(timezone.utc)
    output=ROOT/('observation-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    receipt={'local_started_utc':now.isoformat(),'observer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'scope':'Read-only existing cell; no process arguments/environment, mutation, new container or workload. Bounded log excerpts are supplemental.'}
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=code,text=True,capture_output=True,timeout=60)
        receipt.update(returncode=p.returncode,stderr=p.stderr)
        if p.returncode:receipt['stdout']=p.stdout
        else:receipt.update(json.loads(p.stdout))
    except subprocess.TimeoutExpired as e:
        receipt.update(error=repr(e),stdout=(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else e.stdout,stderr=(e.stderr or b'').decode() if isinstance(e.stderr,bytes) else e.stderr)
    receipt['local_finished_utc']=datetime.now(timezone.utc).isoformat()
    with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(output),'returncode':receipt.get('returncode'),'state':receipt.get('state'),
                     'processes':len(receipt.get('mapping',{}).get('processes',[])),
                     'cgroup':receipt.get('observation',{}).get('cgroup',{}),
                     'log_errors':receipt.get('observation',{}).get('error_scan',{}).get('matches',[])},indent=2))


if __name__=='__main__':main()
