"""Observe public IDENTIFIER validation order, parameters, and scalar/table routes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);ENGINE=sys.argv[2];assert ENGINE in ('spark','sail')
CASES=[
 ('scalar_divide_type',"SELECT IDENTIFIER(1 / 0) AS value FROM input",None),
 ('scalar_integral_type',"SELECT IDENTIFIER(1 DIV 0) AS value FROM input",None),
 ('scalar_remainder_type',"SELECT IDENTIFIER(1 % 0) AS value FROM input",None),
 ('scalar_divide_string',"SELECT IDENTIFIER(CAST(1 DIV 0 AS STRING)) AS value FROM input",None),
 ('typeof_integral',"SELECT IDENTIFIER(CASE WHEN typeof(1 DIV 0) = 'bigint' THEN 'foo' ELSE 'missing' END) AS value FROM input",None),
 ('ordinary_integral',"SELECT 1 DIV 0 AS value",None),
 ('scalar_raise',"SELECT IDENTIFIER(raise_error('boom')) AS value FROM input",None),
 ('scalar_raise_cast',"SELECT IDENTIFIER(CAST(raise_error('boom') AS STRING)) AS value FROM input",None),
 ('scalar_assert',"SELECT IDENTIFIER(assert_true(true)) AS value FROM input",None),
 ('typeof_raise',"SELECT IDENTIFIER(CASE WHEN typeof(raise_error('boom')) = 'void' THEN 'foo' ELSE 'missing' END) AS value FROM input",None),
 ('typeof_assert',"SELECT IDENTIFIER(CASE WHEN typeof(assert_true(true)) = 'void' THEN 'foo' ELSE 'missing' END) AS value FROM input",None),
 ('catalog_typeof_raise',"SET CATALOG typeof(raise_error('boom'))",None),
 ('catalog_typeof_assert',"SET CATALOG typeof(assert_true(true))",None),
 ('catalog_typeof_catalog',"SET CATALOG typeof(current_catalog())",None),
]

def owners():
 r=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);return {'exit_code':r.returncode,'stdout':r.stdout}
report={'started_at':datetime.now(timezone.utc).isoformat(),'engine':ENGINE,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'Public SQL validation phase, condition/state/parameters and rows; not SDP Scala suite acceptance','cases':[]};spark=None
try:
 if ENGINE=='spark':assert owners()=={'exit_code':1,'stdout':''}
 spark=SparkSession.builder.remote('local[1]' if ENGINE=='spark' else 'sc://localhost:50094').appName('identifier constant validation').config('spark.ui.enabled','false').getOrCreate();report['spark_version']=spark.version;assert spark.version=='4.2.1'
 spark.sql('CREATE OR REPLACE TEMPORARY VIEW input AS SELECT 9 AS foo').collect()
 for name,query,args in CASES:
  row={'name':name,'query':query,'args':args};report['cases'].append(row)
  try:
   row['rows']=[r.asDict() for r in spark.sql(query,args=args).collect()];row['returned']=True
  except Exception as error:
   row.update(returned=False,error=str(error),exception_type=type(error).__name__,condition=error.getCondition() if hasattr(error,'getCondition') else None,sql_state=error.getSqlState() if hasattr(error,'getSqlState') else None,parameters=error.getMessageParameters() if hasattr(error,'getMessageParameters') else None)
  print(json.dumps({k:row.get(k) for k in ['name','returned','rows','condition','sql_state','parameters']}),flush=True)
 jars=Path(__import__('pyspark').__file__).parent/'jars';report['installed_client_jars']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in jars.glob('spark-*.jar') if p.name.startswith(('spark-connect_','spark-sql_','spark-pipelines_'))}
finally:
 if spark is not None:spark.stop()
 report['listener_after_stop']=owners();report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
