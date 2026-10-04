"""At most six authorized one-shot logging03 reads. This file contains no loop."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parent
BOOT='f5443bfc-c939-491a-a984-b73cc6d1cb20'
CID='40128227f08843330ed7a20daa987e042a827c0e51b24c562dfd01a48d5765a5'
READER='0b7746b9a89202723ded4c1816b76a89d4ad0f2190c800cb4dcb84b3d34bc460'
CONFIG='b28132996612b11edb77bb02019288e4a562db5e4d22c4430a6a8815a220aea0'
FIRST=datetime.fromisoformat('2026-09-30T22:15:11+00:00')
EXPECTED={185523:(15082028,1),185540:(15082060,7),185584:(15084870,50),185701:(15085029,167),185700:(15085028,166)}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def admit(prior,now):
    if len(prior)>=6:raise RuntimeError('six-read authorization exhausted')
    if now<FIRST:raise RuntimeError('first read not yet authorized')
    if prior:
        previous=prior[-1]
        if previous.get('outcome')!='LIVE_NO_NEW_FAULT_OBSERVED':raise RuntimeError('stop after prior timeout/fault/receipt/identity failure')
        if previous.get('returncode')!=0 or previous.get('capture',{}).get('returncode')!=0:raise RuntimeError('prior remote process did not return zero')
        if now<datetime.fromisoformat(previous['local_finished_utc'])+timedelta(seconds=300):raise RuntimeError('wait >=300s after prior read returned')
    return len(prior)+1

VM_PREFIX=r'''
import json,sys,time
from pathlib import Path
r=json.loads(sys.argv[1]);identity=r['identity'];init=Path('/proc')/str(identity['init_host_pid'])
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot_id'],'boot changed'
assert int((init/'stat').read_text().rsplit(')',1)[1].split()[19])==r['init_start_ticks'],'init PID reused'
cg=(init/'cgroup').read_text();assert cg.strip()=='0::/docker/'+identity['container_id'],'init cgroup differs'
identity['host_pids']=sorted(int(x) for x in (Path('/sys/fs/cgroup')/cg.split('::',1)[1].strip().lstrip('/')/'cgroup.procs').read_text().split())
options={'identity':identity,'root':r['root'],'previous_offset':r['previous_offset']}
sys.argv=['reader',json.dumps(identity),json.dumps(options)]
'''
VM_POST=r'''
init=Path('/proc')/str(identity['init_host_pid'])
checks={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'init_start_ticks':int((init/'stat').read_text().rsplit(')',1)[1].split()[19]),'init_cgroup':(init/'cgroup').read_text()}
assert checks['boot_id']==r['boot_id'],'boot changed during read'
assert checks['init_start_ticks']==r['init_start_ticks'],'init PID reused during read'
assert checks['init_cgroup'].strip()=='0::/docker/'+identity['container_id'],'init cgroup changed during read'
print(json.dumps(checks))
'''
REMOTE=r'''
import hashlib,importlib.util,json,os
from pathlib import Path
from datetime import datetime,timezone
p=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/capture_process_identity.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()==r['reader_sha256']
assert hashlib.sha256((p.parent/'logging03-compact.json').read_bytes()).hexdigest()==r['config_sha256']
spec=importlib.util.spec_from_file_location('reader',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')
record={'remote_started_utc':datetime.now(timezone.utc).isoformat(),'container_id':r['identity']['container_id']}
try:
 code=r['vm_prefix']+m.VM_READER+r['vm_observer']+r['vm_post']
 c=m.run(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-B','-c',code,json.dumps(r)])
 c['command'][-2]='<retained guarded observer source plus pinned identity reader>';c['command'][-1]='<retained request>'
 record['capture']=c
 if c['returncode']==0:
  record['mapping'],record['observation'],record['post_guards']=[json.loads(x) for x in c.pop('stdout').splitlines() if x.strip()]
except Exception as e:record['error']=repr(e)
record['remote_finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(record))
'''

def classify(receipt):
    reasons=[]
    if receipt.get('error') or receipt.get('returncode')!=0 or receipt.get('capture',{}).get('returncode')!=0:
        return 'STOP_CAPTURE_FAILURE',['remote timeout/error/nonzero/invalid capture']
    mapping={x['host_pid']:x for x in receipt['mapping']['processes']}
    for pid,(ticks,ns) in EXPECTED.items():
        row=mapping.get(pid)
        if row is None:reasons.append('expected PID disappeared: '+str(pid));continue
        if row.get('error'):reasons.append('process mapping failed: '+str(pid));continue
        if row['start_ticks']!=ticks or int(row['status']['NSpid'].split()[-1])!=ns or row['cgroup'].strip()!='0::/docker/'+CID:
            reasons.append('expected PID/start/namespace/cgroup identity differs: '+str(pid))
    if any(row.get('error') for row in mapping.values()):reasons.append('one or more observed process mappings failed')
    observation=receipt['observation']
    if observation['boot_id']!=BOOT:reasons.append('boot differs')
    if any(not isinstance(observation['cgroup'].get(name),str) for name in ('memory.current','memory.peak','memory.events')):
        reasons.append('required cgroup read failed')
    if observation['files']['receipt.json']['exists']:reasons.append('producer receipt now exists')
    if observation['error_scan']['matches']:reasons.append('new bounded timestamped runtime fault candidate')
    events=observation['cgroup'].get('memory.events')
    if isinstance(events,str) and int(dict(x.split() for x in events.splitlines()).get('oom_kill','0'))>0:reasons.append('cgroup records OOM kill')
    return ('STOP_NEW_EVIDENCE' if reasons else 'LIVE_NO_NEW_FAULT_OBSERVED'),reasons


def main():
    now=datetime.now(timezone.utc)
    prior=[json.loads(p.read_text()) for p in sorted(ROOT.glob('series-observation-*.json'))]
    ordinal=admit(prior,now)
    initial=json.loads((ROOT/'observation-20260930T220458591359Z.json').read_text())
    latest=prior[-1] if prior else initial
    request={'reader_sha256':READER,'config_sha256':CONFIG,'boot_id':BOOT,'identity':initial['identity'],'init_start_ticks':15082028,
             'root':initial['volume_inspection']['stdout'].strip(),'previous_offset':latest['observation']['error_scan']['next_offset'],
             'vm_prefix':VM_PREFIX,'vm_observer':(ROOT/'vm_observer.py').read_text(),'vm_post':VM_POST}
    assert sha(ROOT.parent/'capture_process_identity.py')==READER and sha(ROOT.parent/'logging03-compact.json')==CONFIG
    output=ROOT/('series-observation-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    receipt={'local_started_utc':now.isoformat(),'ordinal':ordinal,'observer_sha256':sha(Path(__file__)),'vm_observer_sha256':sha(ROOT/'vm_observer.py'),
             'request':{k:v for k,v in request.items() if not k.startswith('vm_')},
             'scope':'One read-only existing-cell observation. Full status/namespace mapping and original sampler/log tails only; no new PSS scan, executable hash, dmesg, argv/environment, Docker call, signal or workload. At most6; >=300s after prior read returned; bounded scan gaps disclosed.'}
    code='import json\nr=json.loads('+repr(json.dumps(request))+')\n'+REMOTE
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=code,text=True,capture_output=True,timeout=60)
        receipt.update(returncode=p.returncode,stderr=p.stderr,raw_remote_stdout=p.stdout)
        if p.returncode==0:receipt.update(json.loads(p.stdout))
    except subprocess.TimeoutExpired as e:
        receipt.update(error='local SSH timeout; remote reader termination unproven',stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
    except Exception as e:receipt['error']=repr(e)
    try:receipt['outcome'],receipt['stop_reasons']=classify(receipt)
    except Exception as e:receipt.update(outcome='STOP_CAPTURE_FAILURE',stop_reasons=['invalid capture structure'],classification_error=repr(e))
    receipt['local_finished_utc']=datetime.now(timezone.utc).isoformat()
    with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(output),'ordinal':ordinal,'outcome':receipt['outcome'],'stop_reasons':receipt['stop_reasons'],'cgroup':receipt.get('observation',{}).get('cgroup',{}),'new_faults':receipt.get('observation',{}).get('error_scan',{}).get('matches',[])},indent=2))

if __name__=='__main__':main()
