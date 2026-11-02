from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,subprocess
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
P=Path(sys.argv[1]);P.mkdir(exist_ok=False);KEY='spark.sql.legacy.allowNegativeScaleOfDecimal'
def listeners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return p.stdout
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'cases':[]};s=None;assert not listeners()
try:
 s=SparkSession.builder.remote('local[2]').appName('decimal-config').config('spark.ui.enabled','false').getOrCreate();r['spark_version']=s.version;assert s.version=='4.2.1';r['default']=s.conf.get(KEY)
 for value in ['true','false',' TrUe\t','\x00true\x00','falſe','FALſE','1','0','yes','','\u00a0true\u00a0','truſe']:
  s.conf.set(KEY,'true');c={'value':value,'before':s.conf.get(KEY)};r['cases'].append(c)
  try:s.conf.set(KEY,value);c['accepted']=True
  except Exception as e:c.update(accepted=False,exception_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
  c['after']=s.conf.get(KEY)
 s.conf.unset(KEY);r['after_unset']=s.conf.get(KEY)
finally:
 if s is not None:s.stop()
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=listeners());(P/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids'];print('Spark decimal boolean12 recorded; no listener')
