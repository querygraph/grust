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
  receipt=json.loads(Path(sys.argv[3]).read_text());assert receipt['outcome']=='passed' and receipt['cli_sha256']==sha(cli);r.update(runtime_commit=receipt['sail_commit'],cli_sha256=sha(cli))
  with(out/'server.log').open('w')as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(port)],cwd=root,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdout=log,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+30
  while not owners():assert process.poll()is None and time.monotonic()<deadline;time.sleep(.1)
  assert owners()==[process.pid];s=SparkSession.builder.remote(f'sc://localhost:{port}').create()
 r['version']=s.version;assert s.version=='4.2.1'

 from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
 from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph
 inputs=json.loads(Path('/tmp/sail-sdp-flow-grammar-inputs.json').read_text())
 for entry in inputs:
  c={'kind':entry['kind'],'label':entry['label'],'sql':entry['sql'],'file':'é;origin.sql','api':'DefineSqlGraphElements'};r['cases'].append(c)
  graph=create_dataflow_graph(s,None,None,None);registry=SparkConnectGraphElementRegistry(s,graph)
  try:registry.register_sql(c['sql'],Path(c['file']));c['outcome']='accepted'
  except Exception as e:c.update(outcome='error',error_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters(),message=str(e))
  c['contains_filename']=c['file'] in c.get('message','')
  c['table_exists']=s.catalog.tableExists('table1')

 test_root=Path('/Users/alexy/src/sail-pipelines-proposal') if mode=='spark' else root
 test_path='python/pysail/tests/spark/pipelines/test_flow_syntax.py'
 expected=subprocess.check_output(['git','-C',str(test_root),'show','25bf10d6e0251767e97b60fb80169f5f27da51de:'+test_path]);assert(test_root/test_path).read_bytes()==expected
 r['test_sha256']=sha(test_root/test_path)
 env={**os.environ,'PYTHONPATH':str(test_root/'python')+os.pathsep+'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','SPARK_REMOTE':f'sc://localhost:{port}'}
 with(out/'pytest.log').open('w')as log:result=subprocess.run([sys.executable,'-m','pytest',test_path,'-q','--junitxml='+str(out/'pytest.xml')],cwd=test_root,env=env,stdout=log,stderr=subprocess.STDOUT)
 r['pytest_exit_code']=result.returncode

finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll()is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listeners=owners());(out/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listeners'];print(mode,'recorded registration failure boundaries')

assert r["pytest_exit_code"]==0
