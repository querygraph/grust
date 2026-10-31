from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,signal,subprocess,sys,time
from pyspark.sql import SparkSession
mode,dest=sys.argv[1:3];out=Path(dest);out.mkdir(exist_ok=False);root=Path('/Users/alexy/src/sail-sdp-gate');cli=root/'target/debug/sail';port=15002 if mode=='spark'else 50095
# Keep independent listener ownership for each backend.
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return sorted(int(x[1:])for x in p.stdout.splitlines()if x.startswith('p'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not owners();r={'started_at':datetime.now(timezone.utc).isoformat(),'mode':mode,'script_sha256':sha(__file__),'cases':[],'cleanup_errors':[]};s=None;process=None
try:
 if mode=='spark':
  for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']:os.environ.pop(k,None)
  os.environ['SPARK_LOCAL_IP']='127.0.0.1';s=SparkSession.builder.remote('local[2]').appName('sdp-direct-ddl').config('spark.sql.warehouse.dir',(out/'warehouse').as_uri()).getOrCreate()
 else:
  receipt=json.loads(Path(sys.argv[3]).read_text());assert receipt['outcome']=='passed' and receipt['sail_commit']=='14eb7766f7efc3c39b1df0df396d13cd9551dc7d'and receipt['cli_sha256']==sha(cli);r.update(runtime_commit=receipt['sail_commit'],cli_sha256=sha(cli))
  with(out/'server.log').open('w')as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(port)],cwd=root,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdout=log,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+30
  while not owners():assert process.poll()is None and time.monotonic()<deadline;time.sleep(.1)
  assert owners()==[process.pid];s=SparkSession.builder.remote(f'sc://localhost:{port}').create()
 r['version']=s.version;assert s.version=='4.2.1'

 from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
 from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph

 from pyspark.sql.connect import proto as pb
 for api in ['sql','protocol']:
  for name,implicit in [('Some_DB.F',False),('`D.b`.`F``Q`',False),('Cat.Db.F',False),('a.b.c.d',False),('`literal.dot`',False),('Cat.Db.F',True),('a.b.c.d',True)]:
   if api=='sql' and implicit:continue
   c={'api':api,'name':name,'implicit':implicit};r['cases'].append(c)
   graph=create_dataflow_graph(s,None,None,None)
   try:
    if api=='sql':
     registry=SparkConnectGraphElementRegistry(s,graph)
     registry.register_sql(f'CREATE STREAMING TABLE st; CREATE FLOW {name} AS INSERT INTO st BY NAME SELECT * FROM STREAM external_t1',Path('names.sql'))
    else:
     command=pb.Command();flow=command.pipeline_command.define_flow;flow.dataflow_graph_id=graph;flow.flow_name=name;flow.target_dataset_name=name if implicit else 'st';flow.relation_flow_details.relation.range.end=1;flow.relation_flow_details.relation.range.step=1
     s.client.execute_command(command)
    c['outcome']='accepted'
   except Exception as e:c.update(outcome='error',error_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters(),message=str(e))

finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll()is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listeners=owners());(out/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listeners'];print(mode,'recorded registration failure boundaries')
