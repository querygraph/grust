"""One read-only VM call using previously established container/boot identity."""
import ast
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
legacy=ROOT/'observe_attempt03.py'
nodes=ast.parse(legacy.read_text()).body
VM_OBSERVER=next(ast.literal_eval(n.value) for n in nodes if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VM_OBSERVER' for t in n.targets))
initial=json.loads((ROOT/'process-identity-01.json').read_text())
first=json.loads((ROOT/'observation-20260930T200923589965Z.json').read_text())
previous=0;last_mapping=datetime.fromisoformat(initial['started_utc']);last_pids=initial['identity']['host_pids']
for p in sorted(ROOT.glob('observation-*.json')):
 d=json.loads(p.read_text());previous=max(previous,d.get('observation',{}).get('error_scan',{}).get('next_offset',0))
 if d.get('mapping',{}).get('processes'):
  when=datetime.fromisoformat(d['started_utc'])
  if when>=last_mapping:last_mapping=when;last_pids=[x['host_pid'] for x in d['mapping']['processes']]
request={'reader_sha256':hashlib.sha256((ROOT.parent/'capture_process_identity.py').read_bytes()).hexdigest(),'vm_observer':VM_OBSERVER,
 'identity':initial['identity'],'boot_id':first['observation']['boot_id'],'init_start_ticks':initial['mapping']['processes'][0]['start_ticks'],
 'root':first['volume_inspection']['stdout'].strip(),'previous_offset':previous,'last_pids':last_pids,
 'capture_mapping':(datetime.now(timezone.utc)-last_mapping).total_seconds()>=300}
VM_PREFIX=r'''
import json,sys,time
from pathlib import Path
r=json.loads(sys.argv[1]);identity=r['identity'];init=Path('/proc')/str(identity['init_host_pid'])
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot_id'],'boot changed'
assert int((init/'stat').read_text().rsplit(')',1)[1].split()[19])==r['init_start_ticks'],'init PID reused'
cg=(init/'cgroup').read_text();assert identity['container_id'] in cg,'init cgroup differs'
pids=sorted(int(p) for p in (Path('/sys/fs/cgroup')/cg.split('::',1)[1].strip().lstrip('/')/'cgroup.procs').read_text().split())
identity['host_pids']=pids if r['capture_mapping'] or pids!=sorted(r['last_pids']) else []
options={'identity':identity,'root':r['root'],'previous_offset':r['previous_offset']}
sys.argv=['reader',json.dumps(identity),json.dumps(options)]
'''
remote="""
import importlib.util,hashlib,os,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
"""+'r=json.loads('+repr(json.dumps(request))+')\n'
remote+="""p=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/capture_process_identity.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()==r['reader_sha256']
spec=importlib.util.spec_from_file_location('reader',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')
record={'started_utc':datetime.now(timezone.utc).isoformat(),'container_id':r['identity']['container_id']}
"""
remote+='code='+repr(VM_PREFIX)+'+m.VM_READER+r[\'vm_observer\']\n'
remote+="""c=m.run(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-c',code,json.dumps(r)])
c['command'][-2]='<retained observer VM prefix, pinned identity reader, retained VM observer>'
record['capture']=c
if c['returncode']==0:
 record['mapping'],record['observation']=[json.loads(x) for x in c.pop('stdout').splitlines() if x.strip()]
 record['state']={'Running':True,'Status':'live_init','source':'matching boot, init start ticks and exact cgroup; not Docker inspection'}
record['finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(record))
"""
now=datetime.now(timezone.utc);out=ROOT/('observation-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
receipt={'local_started_utc':now.isoformat(),'observer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'vm_observer_source_sha256':hashlib.sha256(legacy.read_bytes()).hexdigest(),'scope':'One bounded read-only VM call; boot/init/cgroup guards. No Docker call, new container, target process mutation, argv or environment read.'}
try:
 p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=remote,text=True,capture_output=True,timeout=60)
 receipt.update(returncode=p.returncode,stderr=p.stderr)
 if p.returncode:receipt['stdout']=p.stdout
 else:receipt.update(json.loads(p.stdout))
except subprocess.TimeoutExpired as e:
 receipt.update(error=repr(e),stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
receipt['local_finished_utc']=datetime.now(timezone.utc).isoformat()
with out.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps({'output':str(out),'returncode':receipt.get('returncode'),'capture_returncode':receipt.get('capture',{}).get('returncode')}))
