from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,signal,subprocess,sys,time
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines import spark_connect_pipeline as client
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
mode,dest=sys.argv[1:3];out=Path(dest);out.mkdir(exist_ok=False)
root=Path('/Users/alexy/src/sail-sdp-gate');cli=root/'target/debug/sail';port=15002 if mode=='spark' else 50095
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in (0,1)
 return sorted(int(x[1:])for x in p.stdout.splitlines()if x.startswith('p'))
assert not owners()
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(__file__),'mode':mode,'cases':[],'cleanup_errors':[]};s=None;process=None
B=chr(96)
cases=[('v','v'),('session.v','v'),('system.session.v','v'),('SeSsIoN.v','v'),(f'{B}seſſıon{B}.v','v'),(f'{B}ſyſtem{B}.{B}SESSİON{B}.v','v'),(f'session.{B}a.b{B}','a.b'),('some_database.tv',None),('db.ns.v',None),('system.other.v',None),('system.session.extra.v',None),(f'{B}a.b{B}.{B}c.d{B}',None),(f'db.{B}a{B}{B}b{B}',None),('session.session.v',None),(f'{B}session.v{B}','session.v')]
def quoted(name):return B+name.replace(B,B+B)+B
def details(e):
 return {'error_type':type(e).__name__,'condition':e.getCondition()if hasattr(e,'getCondition')else None,'sql_state':e.getSqlState()if hasattr(e,'getSqlState')else None,'parameters':e.getMessageParameters()if hasattr(e,'getMessageParameters')else None,'message':str(e)}
try:
 if mode=='spark':
  for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']:os.environ.pop(k,None)
  os.environ['SPARK_LOCAL_IP']='127.0.0.1'
  r['spark_source_commit']=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip()
  s=SparkSession.builder.remote('local[2]').appName('sdp-temp-qualifiers').config('spark.sql.warehouse.dir',(out/'warehouse').as_uri()).getOrCreate()
 else:
  receipt=json.loads(Path(sys.argv[3]).read_text());assert receipt['outcome']=='passed' and receipt['cli_sha256']==sha(cli)
  r.update(server_artifact_source_commit=receipt['sail_commit'],cli_sha256=sha(cli),public_receipt_sha256=sha(sys.argv[3]))
  with (out/'server.log').open('w')as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(port)],cwd=root,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdout=log,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+30
  while not owners():
   assert process.poll()is None and time.monotonic()<deadline;time.sleep(.1)
  assert owners()==[process.pid];r['server_pid']=process.pid
  s=SparkSession.builder.remote(f'sc://localhost:{port}').create()
 r['version']=s.version;assert s.version=='4.2.1'
 for api in ['sql','pipeline']:
  for name,view in cases:
   sql=f'CREATE TEMPORARY VIEW {name} AS SELECT 1 AS value'
   if api=='pipeline':sql+='; CREATE MATERIALIZED VIEW mv AS SELECT * FROM '+(quoted(view)if view is not None else name)+';'
   c={'api':api,'name':name,'sql':sql,'expected_valid':view is not None,'phase':'sql'if api=='sql'else'registration'};r['cases'].append(c);graph=None
   try:
    if api=='sql':
     s.sql(sql).collect();c['rows']=[list(x)for x in s.sql('SELECT * FROM '+quoted(view or name)).collect()]
    else:
     graph=client.create_dataflow_graph(s,None,None,None)
     SparkConnectGraphElementRegistry(s,graph).register_sql(sql,Path('qualifier.sql'))
    c['outcome']='accepted'
   except Exception as e:c.update(outcome='error',**details(e))
   finally:
    if graph is not None:
     try:
      command=pb.Command();command.pipeline_command.drop_dataflow_graph.dataflow_graph_id=graph;s.client.execute_command(command)
     except Exception as e:r['cleanup_errors'].append(details(e))
    if api=='sql' and c['outcome']=='accepted':
     try:s.sql('DROP VIEW '+quoted(view or name)).collect()
     except Exception as e:r['cleanup_errors'].append(details(e))
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll()is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listeners=owners());(out/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listeners'] and not r['cleanup_errors'];print(mode,'recorded',len(r['cases']),'temporary view cases')
