from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, signal, subprocess, sys, time
from pyspark.sql import SparkSession
mode, dest = sys.argv[1:3]
out=Path(dest);out.mkdir(exist_ok=False)
port=15002 if mode=='spark' else 50095
root=Path('/Users/alexy/src/sail-sdp-gate');cli=root/'target/debug/sail'
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
 assert p.returncode in (0,1)
 return [int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')]
assert not owners()
r={'started_at':datetime.now(timezone.utc).isoformat(),'mode':mode,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[]}
r['sail_test_commit']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
r['feature_sha256']=hashlib.sha256((root/'python/pysail/tests/spark/pipelines/test_sql_namespace.py').read_bytes()).hexdigest()
r['fixture_sha256']=hashlib.sha256((root/'python/pysail/tests/spark/pipelines/conftest.py').read_bytes()).hexdigest()
if mode=='sail':
 receipt=json.loads(Path(sys.argv[3]).read_text())
 assert receipt['outcome']=='passed' and receipt['sail_commit']=='d99e8b86d4db7aa2c5f79848496e6f3bfad6acb2'
 assert set(subprocess.check_output(['git','-C',str(root),'diff','--name-only',receipt['sail_commit'],r['sail_test_commit']],text=True).splitlines())=={'python/pysail/tests/spark/pipelines/test_sql_namespace.py','python/pysail/tests/spark/pipelines/conftest.py'}
 r['server_artifact_source_commit']=receipt['sail_commit']
 assert receipt['cli_sha256']==hashlib.sha256(cli.read_bytes()).hexdigest()
 r['public_receipt_sha256']=hashlib.sha256(Path(sys.argv[3]).read_bytes()).hexdigest()
s=None;process=None
queries=[]
try:
 if mode=='spark':
  for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
  os.environ['SPARK_LOCAL_IP']='127.0.0.1'
  r['commit']=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip()
  s=SparkSession.builder.remote('local[2]').appName('sdp-original-multipart').config('spark.sql.warehouse.dir',(out/'warehouse').as_uri()).config('spark.ui.enabled','false').getOrCreate()
 else:
  r['commit']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();r['cli_sha256']=hashlib.sha256(cli.read_bytes()).hexdigest()
  with (out/'server.log').open('w') as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(port)],cwd=root,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','SAIL_CATALOG__LIST':'[{name="spark_catalog",type="memory",initial_database=["test_db"]},{name="c_bb3e5598_be3c_4250_a3e1_92c2a75bd3ce",type="memory",initial_database=["default"]}]','SAIL_CATALOG__DEFAULT_CATALOG':'spark_catalog','SAIL_CATALOG__DEFAULT_DATABASE':'["test_db"]'},stdout=log,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+30
  while not owners():
   assert process.poll() is None and time.monotonic()<deadline
   time.sleep(.1)
  assert owners()==[process.pid];r['server_pid']=process.pid
  s=SparkSession.builder.remote(f'sc://localhost:{port}').create()
 r['version']=s.version;assert s.version=='4.2.1'
 for ansi in (True,False):
  s.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  for q in queries:
   c={'ansi':ansi,'expression':q};r['cases'].append(c)
   try:
    df=s.sql('SELECT '+q+' AS value');c['schema']=df.schema.jsonValue();c['rows']=[list(x) for x in df.collect()]
   except Exception as e:
    c.update(error_type=type(e).__name__,message=str(e),condition=e.getCondition() if hasattr(e,'getCondition') else None)
 command=['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','-m','pytest','-q','python/pysail/tests/spark/pipelines/test_sql_namespace.py','python/pysail/tests/spark/pipelines/test_cte_stream.py','--junitxml='+str(out/'features.xml')]
 env={**os.environ,'PYTHONPATH':str(root/'python')+os.pathsep+'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','SPARK_REMOTE':f'sc://localhost:{port}'}
 with (out/'features.log').open('w') as log:result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 r['feature_command']=command;r['feature_exit_code']=result.returncode
 if mode=='sail' and result.returncode==0:
  command=['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','scripts/spark-pipelines-tests/catalog_scope.py','--remote',f'sc://localhost:{port}','--primary-catalog','spark_catalog','--secondary-catalog','c_bb3e5598_be3c_4250_a3e1_92c2a75bd3ce','--warehouse',(out/'combined-warehouse').as_uri(),'--storage',(out/'combined-state').as_uri(),'--report',str(out/'combined.json')]
  with (out/'combined.log').open('w') as log:result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
  r['combined_command']=command;r['combined_exit_code']=result.returncode
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r['remaining_listeners']=owners();r['completed_at']=datetime.now(timezone.utc).isoformat()
 (out/'observations.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
assert not r['remaining_listeners'] and r['feature_exit_code']==0 and r.get('combined_exit_code',0)==0
print(mode, 'recorded',len(r['cases']),'cases')
