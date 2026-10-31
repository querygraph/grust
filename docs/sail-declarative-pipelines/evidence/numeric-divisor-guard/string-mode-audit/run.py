from pathlib import Path
import json,os,subprocess,sys
from datetime import datetime,timezone
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
spark=None;r={'started_at':datetime.now(timezone.utc).isoformat(),'cases':[]}
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in (0,1);return p.stdout
assert not listeners()
try:
 spark=SparkSession.builder.remote('local[2]').appName('ansi-analysis-reuse').config('spark.ui.enabled','false').getOrCreate();r['spark_version']=spark.version
 for ansi in (True,False,True,False):
  spark.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  for query in ["SELECT '7' / '2' AS value", "SELECT '1' / '0' AS value", "SELECT '7' / '2' AS value /* ansi="+str(ansi)+' */',"SELECT 7 / '2' AS value"]:
   c={'query':query,'requested_ansi':ansi,'effective_ansi':spark.conf.get('spark.sql.ansi.enabled')};r['cases'].append(c)
   try:
    f=spark.sql(query);c.update(rows=[list(x) for x in f.collect()],schema=f.schema.jsonValue(),returned=True)
   except Exception as e:c.update(returned=False,condition=e.getCondition() if hasattr(e,'getCondition') else None,error=str(e))
finally:
 if spark is not None:spark.stop()
 r['completed_at']=datetime.now(timezone.utc).isoformat();r['remaining_listener_pids']=listeners();(out/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids']
for c in r['cases']:print(c['requested_ansi'],c['effective_ansi'],c['query'],c.get('rows'),c.get('condition'))
