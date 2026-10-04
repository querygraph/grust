import os,json,hashlib,subprocess,shlex
from pathlib import Path
from datetime import datetime,timezone
base=Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003');root=base/'X1-owner09-observer06-cap-copy01';root.mkdir(mode=0o700)
SSH=['/usr/bin/ssh','-4','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','IdentitiesOnly=yes','-i','/Users/alexy/.ssh/laika','-o','HostKeyAlias=capitola','alexy@192.168.4.61']
SCP=['/usr/bin/scp','-4','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','IdentitiesOnly=yes','-i','/Users/alexy/.ssh/laika','-o','HostKeyAlias=capitola']
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};waits=[]
def pin(p):
 p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def run(argv,label):
 p=subprocess.Popen(argv,env=env,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);o,e=p.communicate(timeout=60)
 ps=subprocess.run(['/bin/ps','-axo','pid=,pgid='],capture_output=True,text=True,check=True);gone=all(int(x.split()[1])!=p.pid for x in ps.stdout.splitlines())
 (root/(label+'.stdout')).write_bytes(o);(root/(label+'.stderr')).write_bytes(e)
 v={'observed_utc':datetime.now(timezone.utc).isoformat(),'argv':argv,'pid':p.pid,'pgid':p.pid,'returncode':p.returncode,'actual_wait_completed':True,'group_absent':gone,'forced_cleanup':False}
 write(root/(label+'.wait.json'),v);waits.append(pin(root/(label+'.wait.json')));assert p.returncode==0 and gone
 return o
def remote(c,l):
 return run(SSH+[shlex.join(['/Users/alexy/src/sail-pecan-integrated/.venv/bin/python','-I','-B','-c',c])],l)
owner=base/'X1-twohost-owner09';obs=base/'X1-memory-observer06'
assert pin(owner/'freeze01.json')['sha256']=='80c4c5729ba40747ef72a3caf6b6744e76d62975ab33383d1d6a6dd2e0f07788'
assert pin(obs/'freeze01.json')['sha256']=='e9280729df8d635124e4923d167c62a63a55da79907532fa59b3501984822ad5'
for f,expected in [(owner/'source-gates02/receipt.json','passed_offline_source_gates'),(base/'X1-control-qualifier07/source-gates02/receipt.json','passed_offline_source_gates'),(obs/'source-gates01/receipt.json','passed_scoped_offline_source_gates')]:
 g=json.loads(f.read_text());assert g['outcome']==expected and all(v['returncode']==0 for v in g['commands']) and g['source_before']==g['source_after']
profiles=[
 (owner,'/Users/alexy/src/grust-benchmark-preparations/sem-completion-20261003/x1-twohost-owner09',[f'x1_{n}.py' for n in ('models','io','remote','worker','actions','owner')]+['freeze01.json']),
 (obs,'/Users/alexy/src/grust-benchmark-preparations/sem-completion-20261003/x1-memory-observer06',['observe_x1.py','darwin_memory.py','control_models.py','owner_models.py','x1_models.py','freeze01.json'])]
records=[]
for number,(src,dest,names) in enumerate(profiles,1):
 before=[pin(src/n) for n in names]
 remote('from pathlib import Path;Path('+repr(dest)+').mkdir(mode=0o700)',f'{number}-prepare')
 for i,n in enumerate(names,1):run(SCP+[str(src/n),'alexy@192.168.4.61:'+dest+'/'+n],f'{number}-copy-{i}')
 code="import json,hashlib;from pathlib import Path;p=Path("+repr(dest)+");print(json.dumps([{'path':str(x),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(p.iterdir())]))"
 after=json.loads(remote(code,f'{number}-remote-after'));byname={Path(x['path']).name:x for x in after}
 for x in before:
  y=byname[Path(x['path']).name];assert (x['bytes'],x['sha256'])==(y['bytes'],y['sha256']) and pin(x['path'])==x
 records.append({'source':str(src),'destination':dest,'before':before,'copied':after,'after':[pin(src/n) for n in names]})
v={'observed_utc':datetime.now(timezone.utc).isoformat(),'outcome':'copied_gated_public_owner09_observer06_sources_only','profiles':records,'actual_waits':waits,'observers_or_engines_started':False,'immutable_closure':True}
write(root/'receipt.json',v);print(json.dumps({'receipt':pin(root/'receipt.json'),'copied_count':sum(len(r['copied']) for r in records)}))
