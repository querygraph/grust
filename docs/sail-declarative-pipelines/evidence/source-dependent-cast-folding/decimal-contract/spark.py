from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,math,hashlib,subprocess
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
P=Path(sys.argv[1]);P.mkdir(exist_ok=False)
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return p.stdout
values=[None,'bad','','1.235','1.245','-1.235','999.994','999.995','99999.999','1e3','123456','1e400','9'*40,'NaN','1.0f','0x1.0p2','\u00a01.2\u00a0','１２.３','١٢.٣','1e٢','0e2147483647','0e2147483648','0.00000000000000000000000000000000000000001','\x001.2\x00']
def value(v):
 if v is None:return None
 if isinstance(v,float) and math.isnan(v):return 'NaN'
 if isinstance(v,float) and math.isinf(v):return '+Infinity' if v>0 else '-Infinity'
 return str(v)
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'cases':[]};spark=None;assert not listeners()
try:
 spark=SparkSession.builder.remote('local[2]').appName('floating-cast').config('spark.ui.enabled','false').getOrCreate();r['spark_version']=spark.version
 for ansi in [True,False]:
  spark.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  for target in ['DECIMAL(5,2)','DECIMAL(38,10)']:
   for is_try in [False,True]:
    for source in values:
     literal='NULL' if source is None else "'"+source+"'";query=f"SELECT {'TRY_CAST' if is_try else 'CAST'}({literal} AS {target}) AS value"
     c={'ansi':ansi,'effective_ansi':spark.conf.get('spark.sql.ansi.enabled'),'target':target,'is_try':is_try,'source':source,'query':query};r['cases'].append(c)
     try:
      frame=spark.sql(query);rows=frame.collect();c.update(returned=True,values=[value(x[0]) for x in rows],schema=frame.schema.jsonValue())
     except Exception as e:c.update(returned=False,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
finally:
 if spark is not None:spark.stop()
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=listeners());(P/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids'];print('Spark decimal cast192 recorded; no listener')
