from pathlib import Path
import os,sys,json,subprocess,hashlib
from datetime import datetime,timezone
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in (0,1);return p.stdout
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'cases':[]};spark=None;assert not listeners()
try:
 spark=SparkSession.builder.remote('local[2]').appName('divmod-row-errors').config('spark.ui.enabled','false').getOrCreate();r['spark_version']=spark.version
 spark.conf.set('spark.sql.ansi.enabled','true')
 for codegen in [True,False]:
  spark.conf.set('spark.sql.codegen.wholeStage',str(codegen).lower())
  for partitions in [1,4]:
   for reverse in [False,True]:
    ids='1 - id' if reverse else 'id'
    query=f"SELECT (CASE WHEN id=0 THEN raise_error('left-row-zero') ELSE 8 END) / CAST(CASE WHEN id=1 THEN concat('right-', CAST(id AS STRING)) ELSE '2' END AS INT) AS value FROM (SELECT {ids} AS id FROM range(0,2,1,{partitions}))"
    c={'query':query,'codegen':codegen,'partitions':partitions,'reverse':reverse,'effective_ansi':spark.conf.get('spark.sql.ansi.enabled'),'effective_codegen':spark.conf.get('spark.sql.codegen.wholeStage')};r['cases'].append(c)
    try:c.update(returned=True,rows=[list(x) for x in spark.sql(query).collect()])
    except Exception as e:
     c.update(returned=False,exception_type=type(e).__name__,condition=e.getCondition(),parameters=e.getMessageParameters(),sql_state=e.getSqlState(),error=str(e))
finally:
 if spark is not None:spark.stop()
 r['completed_at']=datetime.now(timezone.utc).isoformat();r['remaining_listener_pids']=listeners();(out/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids']
for c in r['cases']:print(c['codegen'],c['partitions'],c['reverse'],c.get('condition'),c.get('parameters'))
