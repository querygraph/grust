"""Observe generic missing-catalog diagnostics and raw Connect exception hierarchy."""
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
report={'engine':ENGINE,'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':sha(Path(__file__)),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'generic SQL and Catalog API missing lookup; raw Connect metadata; no writes or full Scala-suite verdict','cases':[]}
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
 for name in ['missing_catalog','a.b','a"b','a`b','雪','', '`a.b`']:
  cases.append(('api_'+repr(name),'api',name))
 for sql in ["SET CATALOG missing_catalog","SET CATALOG 'missing_catalog'","SET CATALOG IDENTIFIER('missing_catalog')","USE CATALOG missing_catalog","USE missing_catalog.db","SELECT * FROM missing_catalog.db.input","SHOW TABLES IN missing_catalog.db","SET CATALOG '`a.b`'","SET CATALOG '`a``b`'"]:
  cases.append(('sql_'+sql,'sql',sql))
 for name,site,text in cases:
  case={'name':name,'site':site,'input':text};report['cases'].append(case);captured.clear()
  try:
   if site=='api':spark.catalog.setCurrentCatalog(text)
   else:case['rows']=[list(row) for row in spark.sql(text).collect()]
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
