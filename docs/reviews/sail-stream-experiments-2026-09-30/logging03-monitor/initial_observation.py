"""One initial logging03 identity/sampler observation. No repeating loop."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parent
READER_SHA='0b7746b9a89202723ded4c1816b76a89d4ad0f2190c800cb4dcb84b3d34bc460'
CONFIG_SHA='b28132996612b11edb77bb02019288e4a562db5e4d22c4430a6a8815a220aea0'
BINARY_SHA='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
BOOT='f5443bfc-c939-491a-a984-b73cc6d1cb20'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

VM_PREFIX=r'''
import json,sys,time
from pathlib import Path
r=json.loads(sys.argv[1]);identity=r['identity'];init=Path('/proc')/str(identity['init_host_pid'])
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot_id'],'boot changed'
initial_start_ticks=int((init/'stat').read_text().rsplit(')',1)[1].split()[19])
if r.get('previous_init_start_ticks') is not None:assert initial_start_ticks==r['previous_init_start_ticks'],'init PID reused'
cg=(init/'cgroup').read_text();assert identity['container_id'] in cg,'init cgroup differs'
options={'identity':identity,'root':r['root'],'previous_offset':r.get('previous_offset',0)}
sys.argv=['reader',json.dumps(identity),json.dumps(options)]
'''
VM_EXE=r'''
import hashlib
result={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'init_start_ticks_before':initial_start_ticks,'monotonic_started':time.monotonic(),'processes':[]}
assert result['boot_id']==r['boot_id'],'boot changed after observation'
init=Path('/proc')/str(identity['init_host_pid'])
result['init_start_ticks_after']=int((init/'stat').read_text().rsplit(')',1)[1].split()[19]);assert result['init_start_ticks_after']==initial_start_ticks,'init PID reused'
assert identity['container_id'] in (init/'cgroup').read_text(),'init cgroup changed'
sail_rows=[x for x in rows if not x.get('error') and x.get('status',{}).get('Name')=='sail']
result['mapped_sail_process_count']=len(sail_rows)
result['hashes_deferred_until_three_live_sail_processes']=len(sail_rows)<3
if len(sail_rows)>=3:
 for row in sail_rows:
  pid,start=row['host_pid'],row['start_ticks'];p=Path('/proc')/str(pid);v={'host_pid':pid,'expected_start_ticks':start}
  try:
   v['start_ticks_before']=int((p/'stat').read_text().rsplit(')',1)[1].split()[19]);assert v['start_ticks_before']==start,'PID reused'
   v['cgroup']=(p/'cgroup').read_text();assert identity['container_id'] in v['cgroup'],'cgroup changed'
   v['executable_target']=str((p/'exe').readlink())
   with (p/'exe').open('rb') as f:v['executable_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
   v['start_ticks_after']=int((p/'stat').read_text().rsplit(')',1)[1].split()[19]);assert v['start_ticks_after']==start,'PID reused'
   assert identity['container_id'] in (p/'cgroup').read_text(),'cgroup changed'
   v['matches_runtime561']=v['executable_sha256']==r['binary_sha256']
  except Exception as e:v['error']=repr(e)
  result['processes'].append(v)
# Same bounded startup-region control used for logging02; no whole-log scan.
p=Path(r['root'])/'sail-stream-experiments-20260930/logging03-compact/cells/stream-log03-compact-r1-scale24-pecan-sssp-delta_star/server.log'
try:
 with p.open('rb') as f:data=f.read(65536)
 result['worker_startup_excerpt']=[line.decode(errors='replace') for line in data.splitlines() if b'worker' in line.lower() and (b'pid' in line.lower() or b'start' in line.lower() or b'launch' in line.lower())][:20]
 result['startup_scan_bytes']=len(data)
except OSError as e:result['startup_error']=repr(e)
result['monotonic_finished']=time.monotonic();print(json.dumps(result))
'''
REMOTE=r'''
import hashlib,importlib.util,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
p=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/capture_process_identity.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()==r['reader_sha256']
config=p.parent/'logging03-compact.json';assert hashlib.sha256(config.read_bytes()).hexdigest()==r['config_sha256']
spec=importlib.util.spec_from_file_location('reader',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')
docker=['/usr/local/bin/docker','--context','colima-sail-gate']
record={'started_utc':datetime.now(timezone.utc).isoformat(),'container':'sail-stream-log03-compact-1'}
try:
 inspection=m.run(docker+['inspect','--format','{{json .Id}} {{json .State}}',record['container']]);record['inspection']=inspection
 if inspection['returncode']!=0:raise RuntimeError('container inspection failed')
 cid,state=inspection['stdout'].strip().split(' ',1);cid=json.loads(cid);state=json.loads(state)
 record.update(container_id=cid,state=state)
 assert len(cid)==64 and all(x in '0123456789abcdef' for x in cid)
 if r.get('previous_container_id') is not None:assert cid==r['previous_container_id'],'container changed'
 if state['Running']:
  top=m.run(docker+['top',cid,'-eo','pid,ppid,comm']);record['top']=top;assert top['returncode']==0
  identity={'container_id':cid,'init_host_pid':state['Pid'],'host_pids':[x['host_pid'] for x in m.parse_top(top['stdout'])]};record['identity']=identity
  volume=m.run(docker+['volume','inspect','--format','{{.Mountpoint}}','sail-extension-targets']);record['volume_inspection']=volume;assert volume['returncode']==0
  r.update(identity=identity,root=volume['stdout'].strip())
  code=r['vm_prefix']+m.VM_READER+r['vm_observer']+r['vm_exe']
  capture=m.run(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-B','-c',code,json.dumps(r)])
  capture['command'][-2]='<retained initial prefix, pinned identity reader, adapted observer, executable reader>'
  capture['command'][-1]='<retained request plus inspected identity/root>'
  record['capture']=capture
  if capture['returncode']==0:
   record['mapping'],record['observation'],record['executable_identity']=[json.loads(x) for x in capture.pop('stdout').splitlines() if x.strip()]
except Exception as e:record['error']=repr(e)
record['finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(record))
'''


def main():
    assert sha(ROOT.parent/'capture_process_identity.py')==READER_SHA
    assert sha(ROOT.parent/'logging03-compact.json')==CONFIG_SHA
    previous=list(ROOT.glob('observation-*.json'))
    request={'reader_sha256':READER_SHA,'config_sha256':CONFIG_SHA,'binary_sha256':BINARY_SHA,'boot_id':BOOT,
             'vm_prefix':VM_PREFIX,'vm_observer':(ROOT/'vm_observer.py').read_text(),'vm_exe':VM_EXE,'previous_offset':0}
    if len(previous)>1:raise RuntimeError('at most two initial observations authorized')
    if previous:
        old=json.loads(previous[0].read_text())
        assert not old.get('error') and old.get('returncode')==0 and old.get('capture',{}).get('returncode')==0,'stop after any failure'
        assert old['state']['Running'] is True,'stop after terminal state'
        assert not old['observation']['error_scan']['matches'],'stop after fault'
        assert old['executable_identity']['mapped_sail_process_count']<3,'initial fully mapped; no further read authorized'
        assert (datetime.now(timezone.utc)-datetime.fromisoformat(old['local_finished_utc'])).total_seconds()>=300,'wait at least five minutes'
        request.update(previous_container_id=old['container_id'],previous_init_start_ticks=old['executable_identity']['init_start_ticks_after'],previous_offset=old['observation']['error_scan']['next_offset'])
    now=datetime.now(timezone.utc);output=ROOT/('observation-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    code='import json\nr=json.loads('+repr(json.dumps(request))+')\n'+REMOTE
    receipt={'local_started_utc':now.isoformat(),'observer_sha256':sha(Path(__file__)),'vm_observer_sha256':sha(ROOT/'vm_observer.py'),'reader_sha256':READER_SHA,'config_sha256':CONFIG_SHA,'expected_boot_id':BOOT,'expected_binary_sha256':BINARY_SHA,'scope':'One initial identity and bounded existing sampler/log observation; no additional PSS scan, process argv/environment, target mutation, new container, kernel read or workload. Executable hashes only after three mapped Sail processes. PID/start/cgroup/boot evidence does not independently assign worker IDs.'}
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=code,text=True,capture_output=True,timeout=60)
        receipt.update(returncode=p.returncode,stderr=p.stderr)
        if p.returncode:receipt['stdout']=p.stdout
        else:receipt.update(json.loads(p.stdout))
    except subprocess.TimeoutExpired as e:
        receipt.update(error='local SSH timeout; remote reader termination unproven',stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
    except Exception as e:receipt.update(error=repr(e))
    receipt['local_finished_utc']=datetime.now(timezone.utc).isoformat()
    with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(output),'returncode':receipt.get('returncode'),'error':receipt.get('error'),'state':receipt.get('state'),'processes':len(receipt.get('mapping',{}).get('processes',[])),'sail_processes':receipt.get('executable_identity',{}).get('mapped_sail_process_count'),'log_errors':receipt.get('observation',{}).get('error_scan',{}).get('matches',[])},indent=2))


if __name__=='__main__':main()
