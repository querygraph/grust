"""Observe public IDENTIFIER validation order, parameters, and scalar/table routes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);ENGINE=sys.argv[2];assert ENGINE in ('spark','sail')
CASES=[
 ('catalog_dead',"SELECT IDENTIFIER(CASE WHEN false THEN current_catalog() ELSE 'foo' END) AS value FROM input",None),
 ('database_dead',"SELECT IDENTIFIER(CASE WHEN false THEN current_database() ELSE 'foo' END) AS value FROM input",None),
 ('timezone_dead',"SELECT IDENTIFIER(CASE WHEN false THEN current_timezone() ELSE 'foo' END) AS value FROM input",None),
 ('user_dead',"SELECT IDENTIFIER(CASE WHEN false THEN current_user() ELSE 'foo' END) AS value FROM input",None),
 ('typeof_catalog',"SELECT IDENTIFIER(CASE WHEN false THEN typeof(current_catalog()) ELSE 'foo' END) AS value FROM input",None),
 ('typeof_catalog_nested',"SELECT IDENTIFIER(CASE WHEN false THEN typeof(concat(current_catalog(), current_database())) ELSE 'foo' END) AS value FROM input",None),
 ('typeof_after_nonfoldable',"SELECT IDENTIFIER(CASE WHEN false THEN concat(current_catalog(), typeof(rand())) ELSE 'foo' END) AS value FROM input",None),
 ('nonfoldable_after_typeof',"SELECT IDENTIFIER(CASE WHEN false THEN concat(typeof(rand()), current_catalog()) ELSE 'foo' END) AS value FROM input",None),
 ('missing_after_catalog',"SELECT IDENTIFIER(concat(current_catalog(), missing)) AS value FROM input",None),
 ('missing_before_catalog',"SELECT IDENTIFIER(concat(missing, current_catalog())) AS value FROM input",None),
 ('typeof_missing',"SELECT IDENTIFIER(typeof(missing)) AS value FROM input",None),
 ('missing_subquery_after_catalog',"SELECT IDENTIFIER(concat(current_catalog(), (SELECT missing FROM input))) AS value FROM input",None),
 ('typeof_scalar_subquery',"SELECT IDENTIFIER(CASE WHEN false THEN typeof((SELECT foo FROM input)) ELSE 'foo' END) AS value FROM input",None),
 ('typeof_scalar_missing_subquery',"SELECT IDENTIFIER(CASE WHEN false THEN typeof((SELECT missing FROM input)) ELSE 'foo' END) AS value FROM input",None),
 ('bound_parameter_after_catalog',"SELECT IDENTIFIER(CASE WHEN false THEN current_catalog() ELSE :col END) AS value FROM input",{'col':'foo'}),
 ('bound_parameter_typeof',"SELECT IDENTIFIER(CASE WHEN false THEN typeof(current_catalog()) ELSE :col END) AS value FROM input",{'col':'foo'}),
 ('udf_typeof',"SELECT IDENTIFIER(typeof('literal')) AS value FROM input",None),
 ('udf_typeof_missing',"SELECT IDENTIFIER(typeof(missing)) AS value FROM input",None),
 ('udf_unique',"SELECT IDENTIFIER(probe_identity('literal')) AS value FROM input",None),
 ('udf_unique_missing',"SELECT IDENTIFIER(probe_identity(missing)) AS value FROM input",None),
]

def owners():
 r=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);return {'exit_code':r.returncode,'stdout':r.stdout}
report={'started_at':datetime.now(timezone.utc).isoformat(),'engine':ENGINE,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'Public SQL validation phase, condition/state/parameters and rows; not SDP Scala suite acceptance','cases':[]};spark=None
try:
 if ENGINE=='spark':assert owners()=={'exit_code':1,'stdout':''}
 spark=SparkSession.builder.remote('local[1]' if ENGINE=='spark' else 'sc://localhost:50094').appName('identifier constant validation').config('spark.ui.enabled','false').getOrCreate();report['spark_version']=spark.version;assert spark.version=='4.2.1'
 try:report['function_resolution_session_order']=spark.conf.get('spark.sql.functionResolution.sessionOrder')
 except Exception as error:report['function_resolution_session_order']=None;report['function_resolution_session_order_error']=str(error)
 spark.sql('CREATE OR REPLACE TEMPORARY VIEW input AS SELECT 9 AS foo').collect()
 registered=False
 for name,query,args in CASES:
  if name.startswith('udf_') and not registered:
   spark.udf.register('typeof',lambda value:'foo',StringType());spark.udf.register('probe_identity',lambda value:'foo',StringType());registered=True
  row={'name':name,'query':query,'args':args,'setup':'python_udfs_typeof_and_probe_identity' if registered else 'builtin_functions'};report['cases'].append(row)
  try:
   row['rows']=[r.asDict() for r in spark.sql(query,args=args).collect()];row['returned']=True
  except Exception as error:
   row.update(returned=False,error=str(error),exception_type=type(error).__name__,condition=error.getCondition() if hasattr(error,'getCondition') else None,sql_state=error.getSqlState() if hasattr(error,'getSqlState') else None,parameters=error.getMessageParameters() if hasattr(error,'getMessageParameters') else None)
  print(json.dumps({k:row.get(k) for k in ['name','returned','rows','condition','sql_state','parameters']}),flush=True)
 jars=Path(__import__('pyspark').__file__).parent/'jars';report['installed_client_jars']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in jars.glob('spark-*.jar') if p.name.startswith(('spark-connect_','spark-sql_','spark-pipelines_'))}
finally:
 if spark is not None:spark.stop()
 report['listener_after_stop']=owners();report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
