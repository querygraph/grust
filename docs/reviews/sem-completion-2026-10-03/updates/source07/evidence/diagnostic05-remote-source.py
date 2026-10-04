import sys,os,json,subprocess,socket,time,uuid,signal,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/Users/alexy/src/grust-benchmark-preparations/sem-completion-20261003/x1-twohost-owner06')
import x1_io,x1_models
import grpc
from pyspark.sql.connect.proto import base_pb2 as pb
from pyspark.sql.connect.proto import base_pb2_grpc as service
root=Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-native-local-rpc-diagnostic05');root.mkdir(mode=0o700)
original=Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-native-tiny05/driver/receipt.json')
target=x1_models.RemoteReceipt.model_validate_json(original.read_bytes()).request.target
before=x1_io.pin(target.binary.path);source_before=x1_io.source(target)
env=x1_io.environment(target,{'SAIL_MODE':'local','RUST_LOG':'info','TOKIO_WORKER_THREADS':'8','RAYON_NUM_THREADS':'8'})
payload_before=x1_io.identities(target)
argv=[str(target.python),'-I','-B','-m','pysail','spark','server','--ip','0.0.0.0','--port','50161']
v={'native_entrypoint':'installed_fat_wheel_python_module_cli','payload_before':[p.model_dump(mode='json') for p in payload_before],'observed_utc':datetime.now(timezone.utc).isoformat(),'source_before':source_before,'binary_before':before.model_dump(mode='json'),'argv':argv,'scope':'Native installed-wheel CLI local-mode SparkVersion RPC diagnosis only; same admitted original Target checked but standalone CLI not executed. No graph data or benchmark. Private native environment loaded host-locally without recording contents.'}
p=None
try:
 with (root/'native.log').open('xb') as log:
  p=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 v.update(native_pid=p.pid,native_pgid=p.pid)
 deadline=time.monotonic()+20
 while True:
  assert p.poll() is None,'native server exited before readiness'
  try:
   with socket.create_connection(('127.0.0.1',50161),timeout=1):break
  except OSError:
   assert time.monotonic()<deadline,'readiness deadline';time.sleep(.1)
 observations=[]
 for host in ('127.0.0.1','192.168.4.61','127.0.0.1','192.168.4.61'):
  started=time.monotonic();item={'endpoint':host+':50161'}
  with grpc.insecure_channel(item['endpoint']) as channel:
   req=pb.AnalyzePlanRequest(session_id=str(uuid.uuid4()),client_type='X1-native-RPC-diagnostic')
   req.user_context.user_id='alexy';req.spark_version.SetInParent()
   try:
    response=service.SparkConnectServiceStub(channel).AnalyzePlan(req,timeout=5)
    item.update(rpc_passed=True,spark_version=response.spark_version.version,session_id_matches=response.session_id==req.session_id)
   except grpc.RpcError as e:
    item.update(rpc_passed=False,code=e.code().name,details=e.details())
  item['elapsed_seconds']=time.monotonic()-started
  observations.append(item)
 v['observations']=observations
except BaseException as e:
 v['error']=repr(e)
finally:
 if p is not None:
  if p.poll() is None:
   assert os.getpgid(p.pid)==p.pid and x1_io.pin(target.binary.path)==before
   p.send_signal(signal.SIGINT);v['sigint_shutdown']=True
  v['native_returncode']=p.wait(timeout=30)
  v['native_wait_completed']=True
  rows=subprocess.check_output(['/bin/ps','-axo','pid=,pgid='],text=True).splitlines()
  v['native_group_absent']=all(int(s.split()[1])!=p.pid for s in rows)
 v.update(source_after=x1_io.source(target),binary_after=x1_io.pin(target.binary.path).model_dump(mode='json'),finished_utc=datetime.now(timezone.utc).isoformat())
 payload_after=x1_io.identities(target);assert payload_before==payload_after
 v['payload_after']=[p.model_dump(mode='json') for p in payload_after]
 v['immutable_closure']=v['source_before']==v['source_after'] and v['binary_before']==v['binary_after']
 (root/'receipt.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({'observations':v.get('observations'),'error':v.get('error'),'native_returncode':v.get('native_returncode'),'native_group_absent':v.get('native_group_absent'),'immutable_closure':v['immutable_closure']}))
assert v.get('native_returncode')==0 and v.get('native_group_absent') and v['immutable_closure']
