"""Observe arithmetic lowering, type-only parents and runtime errors."""
from __future__ import annotations
import hashlib,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql.connect.client import core
import pyspark
OUT=Path(sys.argv[1]);ENGINE=sys.argv[2];assert ENGINE in ('spark','sail');OUT.mkdir(exist_ok=False)
def sha(path: Path) -> str:return hashlib.sha256(path.read_bytes()).hexdigest()
def listener() -> dict:
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in (0,1);return {'exit_code':p.returncode,'stdout':p.stdout}
if ENGINE=='spark':assert listener()=={'exit_code':1,'stdout':''}
report={'engine':ENGINE,'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':sha(Path(__file__)),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'40 ANSI/legacy arithmetic SQL probes with raw Connect metadata; no data writes or full Scala-suite verdict','cases':[]}
spark=None;captured=[];original=core.convert_exception
def capture(*args,**kwargs):
 info=args[0] if args else kwargs['info'];captured.append({'reason':info.reason,'domain':info.domain,'metadata':dict(info.metadata)})
 return original(*args,**kwargs)
core.convert_exception=capture
try:
 spark=(SparkSession.builder.remote('local[2]' if ENGINE=='spark' else 'sc://localhost:50094').appName('missing catalog diagnostics').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(OUT/'warehouse').as_uri()).getOrCreate())
 report['spark_version']=spark.version;assert spark.version=='4.2.1'
 report['installed_client_jars']={p.name:sha(p) for p in (Path(pyspark.__file__).parent/'jars').glob('spark-*4.2.1.jar') if any(k in p.name for k in ('pipelines','sql_','connect_'))}
 namespace=[spark.catalog.currentCatalog(),spark.catalog.currentDatabase()];report['session_namespace']=namespace
 cases=[]
 for ansi in [True,False]:
  for name,query in [
   ('typeof_div','SELECT typeof(1 DIV 0) AS value'),
   ('typeof_divide','SELECT typeof(1 / 0) AS value'),
   ('typeof_mod','SELECT typeof(1 % 0) AS value'),
   ('typeof_cast','SELECT typeof(CAST(1 DIV 0 AS STRING)) AS value'),
   ('typeof_rows','SELECT typeof(1 DIV 0) AS value FROM VALUES (1),(2) AS v(id)'),
   ('raw_div','SELECT 1 DIV 0 AS value'),
   ('raw_divide','SELECT 1 / 0 AS value'),
   ('raw_mod','SELECT 1 % 0 AS value'),
   ('dead_div','SELECT CASE WHEN false THEN 1 DIV 0 ELSE 7 END AS value'),
   ('dead_divide','SELECT CASE WHEN false THEN 1 / 0 ELSE 7 END AS value'),
   ('dead_mod','SELECT CASE WHEN false THEN 1 % 0 ELSE 7 END AS value'),
   ('coalesce','SELECT coalesce(7, 1 DIV 0) AS value'),
   ('null_div','SELECT CAST(NULL AS BIGINT) DIV 0 AS value'),
   ('null_divide','SELECT CAST(NULL AS DOUBLE) / 0 AS value'),
   ('null_mod','SELECT CAST(NULL AS INT) % 0 AS value'),
   ('double_mod','SELECT 1.0D % 0.0D AS value'),
   ('input_div','SELECT 7 DIV id AS value FROM VALUES (0) AS v(id)'),
   ('input_divide','SELECT 7 / id AS value FROM VALUES (0) AS v(id)'),
   ('input_mod','SELECT 7 % id AS value FROM VALUES (0) AS v(id)'),
   ('success','SELECT 7 DIV 2 AS quotient, 7 % 2 AS remainder'),
  ]:
   cases.append((('ansi_' if ansi else 'legacy_')+name,ansi,query))
 for name,ansi,text in cases:
  spark.conf.set('spark.sql.ansi.enabled',str(ansi).lower())
  case={'name':name,'ansi_mode':ansi,'query':text};report['cases'].append(case);captured.clear()
  try:
   case['rows']=[list(row) for row in spark.sql(text).collect()]
   case['returned']=True
  except Exception as error:
   case.update(returned=False,error=str(error),exception_type=type(error).__name__)
   for method,key in [('getCondition','condition'),('getMessageParameters','parameters'),('getSqlState','sql_state')]:
    try:case[key]=getattr(error,method)()
    except Exception:case[key]=None
  case['connect_errors']=captured.copy()
  case['session_namespace']=[spark.catalog.currentCatalog(),spark.catalog.currentDatabase()]
  assert case['session_namespace']==namespace
finally:
 core.convert_exception=original
 if spark is not None:spark.stop()
 report['listener_after_stop']=listener();report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps([{'name':c['name'],'returned':c['returned'],'condition':c.get('condition'),'exception_type':c.get('exception_type'),'parameters':c.get('parameters'),'connect_errors':c['connect_errors']} for c in report['cases']],indent=2,ensure_ascii=False))
