from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, signal, subprocess, sys, time
from pyspark.sql import SparkSession
mode, dest = sys.argv[1:]
out=Path(dest);out.mkdir(exist_ok=False)
port=15002 if mode=='spark' else 50095
root=Path('/Users/alexy/src/sail-sdp-gate');cli=root/'target/debug/sail'
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
 assert p.returncode in (0,1)
 return [int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')]
assert not owners()
r={'started_at':datetime.now(timezone.utc).isoformat(),'mode':mode,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[]}
s=None;process=None
queries=[
 "nvl2('sentinel', 1, 2)",
 "nvl2(CAST(NULL AS STRING), 1, 2)",
 "nvl2(array(1), 1, 2)",
 "nvl2(TRUE, 1, 2)",
 "nvl2('sentinel', 1, CAST(2 AS BIGINT))",
 "nvl2('sentinel', 1, CAST('bad' AS INT))",
 "nvl2(NULL, CAST('bad' AS INT), 2)",
 "nvl2('sentinel', CAST(1 AS DECIMAL(5,2)), CAST(2 AS DECIMAL(7,3)))",
]
try:
 if mode=='spark':
  for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
  os.environ['SPARK_LOCAL_IP']='127.0.0.1'
  r['commit']=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip()
  s=SparkSession.builder.remote('local[2]').appName('sdp-nvl2').config('spark.ui.enabled','false').getOrCreate()
 else:
  r['commit']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();r['cli_sha256']=hashlib.sha256(cli.read_bytes()).hexdigest()
  with (out/'server.log').open('w') as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(port)],cwd=root,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdout=log,stderr=subprocess.STDOUT)
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
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r['remaining_listeners']=owners();r['completed_at']=datetime.now(timezone.utc).isoformat()
 (out/'observations.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
assert not r['remaining_listeners']
print(mode, 'recorded',len(r['cases']),'cases')
