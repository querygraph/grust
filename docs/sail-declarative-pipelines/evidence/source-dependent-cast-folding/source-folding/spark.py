from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,subprocess,tempfile,shutil
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
P=Path(sys.argv[1]);P.mkdir(exist_ok=False)
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return p.stdout
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'cases':[]};s=None;temp=None;assert not listeners()
try:
 s=SparkSession.builder.remote('local[2]').appName('source-folding').config('spark.ui.enabled','false').getOrCreate();r['spark_version']=s.version;assert s.version=='4.2.1'
 temp=Path(tempfile.mkdtemp(prefix='sdp-source-folding-'))
 for name,value in [('pq_null',None),('pq_zero',0)]:
  path=temp/name;s.createDataFrame([(value,)],'d int').write.parquet(str(path));s.read.parquet(str(path)).createOrReplaceTempView(name)
 for ansi in [True,False]:
  s.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  for target in ['INT','DOUBLE','DECIMAL(5,2)','DECIMAL(38,10)']:
   cast=f"CAST('bad' AS {target})"
   cases=[('values_null',f'SELECT {cast} / d AS v FROM VALUES (CAST(NULL AS INT)) AS t(d)'),('parquet_null',f'SELECT {cast} / d AS v FROM pq_null'),('parquet_zero',f'SELECT {cast} / d AS v FROM pq_zero'),('foldable_null',f'SELECT {cast} / CAST(NULL AS INT) AS v'),('foldable_null_over_parquet',f'SELECT {cast} / CAST(NULL AS INT) AS v FROM pq_null'),('case_branch_parquet',f'SELECT CASE WHEN d IS NULL THEN 1 ELSE {cast} END AS v FROM pq_null'),('identifier_null',f'SELECT 1 FROM IDENTIFIER(CAST({cast} / CAST(NULL AS INT) AS STRING))')]
   for name,query in cases:
    c={'ansi':ansi,'effective_ansi':s.conf.get('spark.sql.ansi.enabled'),'target':target,'case':name,'query':query};r['cases'].append(c);phase='sql'
    try:
     frame=s.sql(query);phase='explain';frame.explain();c['explain']='passed';phase='collect';rows=frame.collect();c.update(returned=True,rows=[list(x) for x in rows],schema=frame.schema.jsonValue())
    except Exception as e:c.update(returned=False,phase=phase,exception_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
finally:
 if s is not None:s.stop()
 if temp is not None:shutil.rmtree(temp)
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=listeners());(P/'observations.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
assert not r['remaining_listener_pids'];print('Spark source-folding56 recorded; no listener')
