import sys,os,json,subprocess,socket,time,uuid,signal,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/Users/alexy/src/grust-benchmark-preparations/sem-completion-20261003/x1-twohost-owner06')
import x1_io,x1_models
import grpc
from pyspark.sql.connect.proto import base_pb2 as pb
from pyspark.sql.connect.proto import base_pb2_grpc as service
root=Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-native-local-rpc-diagnostic07');root.mkdir(mode=0o700)
original=Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-native-tiny05/driver/receipt.json')
target=x1_models.RemoteReceipt.model_validate_json(original.read_bytes()).request.target
before=x1_io.pin(target.binary.path);source_before=x1_io.source(target)
env=x1_io.environment(target,{'SAIL_MODE':'local','RUST_LOG':'info','TOKIO_WORKER_THREADS':'8','RAYON_NUM_THREADS':'8'})
argv=[str(target.binary.path),'spark','server','--ip','0.0.0.0','--port','50161']
v={'observed_utc':datetime.now(timezone.utc).isoformat(),'source_before':source_before,'binary_before':before.model_dump(mode='json'),'argv':argv,'scope':'Native local-mode SparkVersion RPC diagnosis only. No graph data or benchmark. Private native environment loaded host-locally without recording contents.'}
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
 for host in ('192.168.4.61','127.0.0.1'):
  item={'endpoint':host+':50161'}
  with grpc.insecure_channel(item['endpoint']) as channel:
   req=pb.AnalyzePlanRequest(session_id=str(uuid.uuid4()),client_type='X1-native-RPC-diagnostic')
   req.user_context.user_id='alexy';req.spark_version.SetInParent()
   try:
    response=service.SparkConnectServiceStub(channel).AnalyzePlan(req,timeout=5)
    item.update(rpc_passed=True,spark_version=response.spark_version.version,session_id_matches=response.session_id==req.session_id)
   except grpc.RpcError as e:
    item.update(rpc_passed=False,code=e.code().name,details=e.details())
  observations.append(item)
 v['observations']=observations
 import shlex
 raw=[]
 for host in ('127.0.0.1','192.168.4.61'):
  item={'endpoint':host+':50161'}
  try:
   with socket.create_connection((host,50161),timeout=3) as sock:
    sock.sendall(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'+b'\x00\x00\x00\x04\x00\x00\x00\x00\x00')
    item['first_http2_header_hex']=sock.recv(9).hex()
  except OSError as e:item.update(error=str(e),errno=e.errno)
  raw.append(item)
 v['raw_http2']=raw
 cross_code="import json,grpc,uuid\nfrom pyspark.sql.connect.proto import base_pb2 as pb\nfrom pyspark.sql.connect.proto import base_pb2_grpc as service\nobs=[]\nwith grpc.insecure_channel('192.168.4.61:50161') as channel:\n r={'host':'morrobay','destination':'192.168.4.61:50161','method':'Health/Check'}\n try:r.update(returned=True,response_hex=channel.unary_unary('/grpc.health.v1.Health/Check')(b'',timeout=4).hex())\n except grpc.RpcError as e:r.update(returned=False,code=e.code().name,details=e.details())\n obs.append(r)\n req=pb.AnalyzePlanRequest(session_id=str(uuid.uuid4()));req.user_context.user_id='alexy';req.spark_version.SetInParent()\n r={'host':'morrobay','destination':'192.168.4.61:50161','method':'AnalyzePlan.spark_version','session_id':req.session_id}\n try:\n  out=service.SparkConnectServiceStub(channel).AnalyzePlan(req,timeout=4);r.update(returned=True,version=out.spark_version.version,session_matches=out.session_id==req.session_id)\n except grpc.RpcError as e:r.update(returned=False,code=e.code().name,details=e.details())\n obs.append(r)\nprint(json.dumps(obs))\n"
 reverse=['/usr/bin/ssh','-4','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','IdentitiesOnly=yes','-i','/Users/alexy/.ssh/laika','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/tmp/morrobay-x1-inventory-20261003T2155Z/morrobay-known_hosts','-o','GlobalKnownHostsFile=/dev/null','-o','HostKeyAlias=morrobay-sem-native','alexy@192.168.4.63',shlex.join(['/Users/alexy/src/grust-benchmark-envs/sem-completion-20261003/x1-fat-x8601/bin/python','-I','-B','-c',cross_code])]
 cp=subprocess.Popen(reverse,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')})
 co,ce=cp.communicate(timeout=25)
 (root/'crosshost.stdout').write_bytes(co);(root/'crosshost.stderr').write_bytes(ce)
 rows=subprocess.check_output(['/bin/ps','-axo','pid=,pgid='],text=True).splitlines()
 v['crosshost_actual_wait']={'pid':cp.pid,'pgid':cp.pid,'returncode':cp.returncode,'wait_completed':True,'group_absent':all(int(row.split()[1])!=cp.pid for row in rows),'forced_cleanup':False}
 assert cp.returncode==0 and v['crosshost_actual_wait']['group_absent']
 v['crosshost']=json.loads(co)

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
 v['immutable_closure']=v['source_before']==v['source_after'] and v['binary_before']==v['binary_after']
 (root/'receipt.json').write_text(json.dumps(v,indent=2)+'\n')
print(json.dumps({'observations':v.get('observations'),'raw_http2':v.get('raw_http2'),'crosshost':v.get('crosshost'),'error':v.get('error'),'native_returncode':v.get('native_returncode'),'native_group_absent':v.get('native_group_absent'),'immutable_closure':v['immutable_closure']}))
assert v.get('native_returncode')==0 and v.get('native_group_absent') and v['immutable_closure']
