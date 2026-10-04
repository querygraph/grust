import json,hashlib,subprocess,sys,os,signal,time
from pathlib import Path
from datetime import datetime,timezone
def owned_group_members(pid):
 rows=subprocess.run(['/bin/ps','-axo','pid=,pgid=,uid='],capture_output=True,text=True,check=True).stdout.splitlines()
 members=[]
 for row in rows:
  process,group,user=map(int,row.split())
  if group==pid:
   assert user==os.getuid()
   try:session=os.getsid(process)
   except ProcessLookupError:continue
   assert session==pid
   members.append(process)
 return members

b=Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003');r=b/'X1-scale24-02-independent-math-root01';r.mkdir(mode=0o700)
def pin(f):
 f=Path(f);h=hashlib.sha256()
 with f.open('rb') as s:
  while block:=s.read(1048576):h.update(block)
 return {'path':str(f),'bytes':f.stat().st_size,'sha256':h.hexdigest()}
p=json.loads((b/'X1-scale24-root-plan02/plan.json').read_text());d=b/'X1-native-scale24-02-whole-store-copy01/whole-run/native13'
v=json.loads((b/'X1-full-oracle02/config-template.json').read_text());inp=Path('/Users/alexy/src/grust-benchmark-data/sem-completion-20261003/x1-original-scale24-restore02/scale24')
v.update(dataset='graph500-generated-scale24',vertices=[pin(f) for f in sorted((inp/'vertices.parquet').rglob('*.parquet'))],edges=[pin(f) for f in sorted((inp/'edges.parquet').rglob('*.parquet'))],expected_vertices=16777216,expected_edges=268435456,source_id=13507776,max_levels=8,partitions=32,edge_schema_profile='original_weight3',result={'directory':str(d),'files':{str(f.relative_to(d)):{k:z for k,z in pin(f).items() if k!='path'} for f in sorted(d.rglob('*')) if f.is_file()}},client_files=p['worker1']['client_files'],producer_evidence=[pin(Path(p['root'])/'receipt.json'),pin(Path(p['root'])/'closed-evidence/client/action-receipt.json'),pin(b/'X1-native-scale24-02-whole-store-copy01/receipt.json'),pin(b/'X1-root-wait-native-scale24-02/wait-receipt.json')],output=str(b/'X1-scale24-02-independent-full-oracle01'),limits={'batch_rows':65536,'work_seconds':7200,'audit_seconds':1200})
sys.path.insert(0,str(b/'X1-full-oracle02'));import bfs_models
parsed=bfs_models.Config.model_validate_json(json.dumps(v));cfg=r/'config.json';cfg.write_text(json.dumps(parsed.model_dump(mode='json'),indent=2)+'\n')
boot="import runpy,sys;sys.path.insert(0,"+repr(str(b/'X1-full-oracle02'))+");runpy.run_path("+repr(str(b/'X1-full-oracle02/bfs_oracle.py'))+",run_name='__main__')"
argv=['/tmp/sem-output-oracle-venv/bin/python','-I','-B','-c',boot,'--config',str(cfg)]
proc=subprocess.Popen(argv,start_new_session=True,env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','AWS_','MINIO_','PYTHON','DYLD_'))},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
cleanup_requested=False;signals=[];interruption=None
try:
 (r/'child-launch.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'pid':proc.pid,'pgid':proc.pid,'argv':argv,'configuration':pin(cfg)},indent=2)+'\n')
 o,e=proc.communicate(timeout=9000)
except BaseException as error:
 cleanup_requested=True;interruption=repr(error)
 for sig,grace in [(signal.SIGINT,60),(signal.SIGTERM,60),(signal.SIGKILL,60)]:
  members=owned_group_members(proc.pid)
  if members:
   try:os.killpg(proc.pid,sig);signals.append(int(sig))
   except ProcessLookupError:pass
  try:o,e=proc.communicate(timeout=grace)
  except subprocess.TimeoutExpired:continue
  until=time.monotonic()+grace
  while owned_group_members(proc.pid) and time.monotonic()<until:time.sleep(0.05)
  if not owned_group_members(proc.pid):break
 else:raise RuntimeError('owned child did not close after declared termination')

(r/'termination.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'cleanup_requested':cleanup_requested,'interruption':interruption,'signals':signals,'scope':'Only the directly launched owned oracle group; interruption and timeout retained as failed.'},indent=2)+'\n')
(r/'stdout').write_bytes(o);(r/'stderr').write_bytes(e)
ps=subprocess.run(['/bin/ps','-axo','pid=,pgid='],capture_output=True,text=True,check=True);gone=all(int(l.split()[1])!=proc.pid for l in ps.stdout.splitlines())
wait={'observed_utc':datetime.now(timezone.utc).isoformat(),'argv':argv,'pid':proc.pid,'pgid':proc.pid,'returncode':proc.returncode,'actual_wait_completed':True,'group_absent':gone,'forced_cleanup':cleanup_requested};(r/'wait.json').write_text(json.dumps(wait,indent=2)+'\n')
out=Path(v['output'])/'receipt.json';res=json.loads(out.read_text());final={'observed_utc':datetime.now(timezone.utc).isoformat(),'configuration':pin(cfg),'actual_wait':pin(r/'wait.json'),'oracle':pin(out),'oracle_outcome':res['outcome'],'scope':'Independent full mathematical and physical certificate for the complete original scale24 output. Original producer/waits are separately bound; this oracle does not certify process/ABI closure.'};(r/'receipt.json').write_text(json.dumps(final,indent=2)+'\n');print(json.dumps({'receipt':pin(r/'receipt.json'),'outcome':res['outcome'],'returncode':proc.returncode,'group_absent':gone,'errors':res['errors'],'failures':res['failures']}));assert proc.returncode==0 and gone and not cleanup_requested and res['outcome']=='passed_full_undirected_BFS_certificate'
