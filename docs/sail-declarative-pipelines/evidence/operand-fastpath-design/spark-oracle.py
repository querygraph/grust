from pathlib import Path
import os,sys,json,hashlib,subprocess
from datetime import datetime,timezone
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return p.stdout
report={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'cases':[]};spark=None;assert not listeners()
try:
 spark=SparkSession.builder.remote('local[2]').appName('conditional-cast-spark').config('spark.ui.enabled','false').getOrCreate();report['spark_version']=spark.version
 for ansi in [True,False]:
  spark.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  for target in ['INT','DOUBLE','DECIMAL(5,2)','DECIMAL(38,10)']:
   for zero in [False,True]:
    right='0' if zero else 'CAST(NULL AS INT)'
    query=f"SELECT CAST('bad' AS {target}) / d AS value FROM VALUES ({right}) AS v(d)"
    case={'ansi':ansi,'effective_ansi':spark.conf.get('spark.sql.ansi.enabled'),'target':target,'zero':zero,'query':query};report['cases'].append(case)
    try:
     frame=spark.sql(query);rows=frame.collect();case.update(returned=True,rows=len(rows),all_null=all(r[0] is None for r in rows),schema=frame.schema.jsonValue())
    except Exception as error:case.update(returned=False,exception_type=type(error).__name__,condition=error.getCondition(),sql_state=error.getSqlState(),parameters=error.getMessageParameters(),error=str(error))
finally:
 if spark is not None:spark.stop()
 report.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=listeners());(out/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
assert not report['remaining_listener_pids']
print('Spark conditional cast16 recorded; no listener')
