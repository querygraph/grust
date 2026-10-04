import json,hashlib,os,subprocess,shlex,signal,time
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

b=Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003');r=b/'X1-native-scale24-02-whole-store-copy01';r.mkdir(mode=0o700);dest=r/'whole-run';dest.mkdir(mode=0o700)
marker=json.loads(Path('/tmp/morrobay-sem-completion-heavy.lock/owner.json').read_text());assert marker['token']=='3078c81a41f844baae8a1752128cfa82'
helper=b/'MinIO-native-preparation01/support';py='/Users/alexy/src/grust-benchmark-envs/sem-completion-20261003/x1-fat-x8601/bin/python'
worker_code="import json,sys,posixpath;from pathlib import Path;sys.path.insert(0,"+repr(str(helper))+");import credential_env;import pyarrow.fs as fs;c=credential_env.read_credentials(Path('/Users/alexy/.local/state/querygraph/x1-minio-store02/credentials.json'));f=fs.S3FileSystem(access_key=c.access_key.get_secret_value(),secret_key=c.secret_key.get_secret_value(),endpoint_override='192.168.4.61:49190',scheme='http',region='us-east-1');prefix='qg-x1-native-20261004b/x1-native-scale24-02/';d=Path("+repr(str(dest))+");a=[x for x in f.get_file_info(fs.FileSelector(prefix.rstrip('/'),recursive=True)) if x.type==fs.FileType.File];assert a;before=sorted((x.path,x.size) for x in a);\nfor x in a:\n rel=x.path.removeprefix(prefix);assert rel!=x.path and '..' not in Path(rel).parts and not Path(rel).is_absolute();p=d/rel;p.parent.mkdir(parents=True,exist_ok=True);\n with f.open_input_stream(x.path) as inp,p.open('xb') as out:\n  while block:=inp.read(1048576):out.write(block)\n assert p.stat().st_size==x.size\nafter=sorted((x.path,x.size) for x in f.get_file_info(fs.FileSelector(prefix.rstrip('/'),recursive=True)) if x.type==fs.FileType.File);assert before==after;print(json.dumps({'source_directory_before':before,'source_directory_after':after,'downloaded_all':True}))"
code=worker_code
known=b/'X1-local-network-diagnostic01/known_hosts'
argv=['/usr/bin/ssh','-4','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','IdentitiesOnly=yes','-i','/Users/alexy/.ssh/laika','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','GlobalKnownHostsFile=/dev/null','-o','HostKeyAlias=morrobay-sem-native','alexy@192.168.4.63',shlex.join([py,'-I','-B','-c',code])]
p=subprocess.Popen(argv,start_new_session=True,env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','AWS_','MINIO_'))},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
cleanup_requested=False;signals=[];interruption=None
try:
 (r/'child-launch.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'pid':p.pid,'pgid':p.pid,'argv':argv},indent=2)+'\n')
 o,e=p.communicate(timeout=900)
except BaseException as error:
 cleanup_requested=True;interruption=repr(error)
 for sig,grace in [(signal.SIGINT,60),(signal.SIGTERM,60),(signal.SIGKILL,60)]:
  members=owned_group_members(p.pid)
  if members:
   try:os.killpg(p.pid,sig);signals.append(int(sig))
   except ProcessLookupError:pass
  try:o,e=p.communicate(timeout=grace)
  except subprocess.TimeoutExpired:continue
  until=time.monotonic()+grace
  while owned_group_members(p.pid) and time.monotonic()<until:time.sleep(0.05)
  if not owned_group_members(p.pid):break
 else:raise RuntimeError('owned child did not close after declared termination')

(r/'termination.json').write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'cleanup_requested':cleanup_requested,'interruption':interruption,'signals':signals},indent=2)+'\n')
(r/'stdout').write_bytes(o);(r/'stderr').write_bytes(e)
ps=subprocess.run(['/bin/ps','-axo','pid=,pgid='],capture_output=True,text=True,check=True);gone=all(int(l.split()[1])!=p.pid for l in ps.stdout.splitlines())
wait={'observed_utc':datetime.now(timezone.utc).isoformat(),'argv':argv,'pid':p.pid,'pgid':p.pid,'returncode':p.returncode,'actual_wait_completed':True,'group_absent':gone,'forced_cleanup':cleanup_requested};(r/'copy.wait.json').write_text(json.dumps(wait,indent=2)+'\n');assert p.returncode==0 and gone and not cleanup_requested
def pin(f):
 h=hashlib.sha256()
 with f.open('rb') as stream:
  while block:=stream.read(1048576):h.update(block)
 return {'path':str(f),'bytes':f.stat().st_size,'sha256':h.hexdigest()}
files=[pin(f) for f in sorted(dest.rglob('*')) if f.is_file()];assert not any(f.is_symlink() for f in dest.rglob('*')) and len(list((dest/'native13').rglob('*.parquet')))>0
v={'observed_utc':datetime.now(timezone.utc).isoformat(),'outcome':'copied_complete_owned_run_prefix_unqualified','producer':pin(Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-native-scale24-02/receipt.json')),'actual_wait':pin(r/'copy.wait.json'),'files':files,'full_output_math_or_process_qualified':False,'scope':'Whole dedicated run prefix retained, including final native13 and separate auxiliary objects; no production bucket or credentials in this receipt.'}
(r/'receipt.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'receipt':pin(r/'receipt.json'),'files':len(files),'native13_parquets':len(list((dest/'native13').rglob('*.parquet')))}))
