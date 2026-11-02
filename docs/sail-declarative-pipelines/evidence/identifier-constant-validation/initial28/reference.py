"""Observe public IDENTIFIER validation order, parameters, and scalar/table routes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);ENGINE=sys.argv[2];assert ENGINE in ('spark','sail')
CASES=[
 ('table_concat',"SELECT * FROM IDENTIFIER(concat('in', 'put'))",None),
 ('table_cast',"SELECT * FROM IDENTIFIER(CAST('input' AS STRING))",None),
 ('table_null','SELECT * FROM IDENTIFIER(NULL)',None),
 ('table_typed_null','SELECT * FROM IDENTIFIER(CAST(NULL AS STRING))',None),
 ('table_integer','SELECT * FROM IDENTIFIER(1)',None),
 ('table_integer_division','SELECT * FROM IDENTIFIER(1 DIV 0)',None),
 ('table_string_division','SELECT * FROM IDENTIFIER(CAST(1 DIV 0 AS STRING))',None),
 ('table_random','SELECT * FROM IDENTIFIER(rand())',None),
 ('table_random_cast','SELECT * FROM IDENTIFIER(CAST(rand() AS STRING))',None),
 ('table_dead_random',"SELECT * FROM IDENTIFIER(CASE WHEN false THEN CAST(rand() AS STRING) ELSE 'input' END)",None),
 ('table_subquery','SELECT * FROM IDENTIFIER((SELECT foo FROM input))',None),
 ('table_subquery_missing_column','SELECT * FROM IDENTIFIER((SELECT missing FROM input))',None),
 ('table_subquery_missing_table','SELECT * FROM IDENTIFIER((SELECT foo FROM absent))',None),
 ('table_named','SELECT * FROM IDENTIFIER(:tab)',{'tab':'input'}),
 ('table_named_concat',"SELECT * FROM IDENTIFIER(:prefix || 'put')",{'prefix':'in'}),
 ('table_positional','SELECT * FROM IDENTIFIER(?)',['input']),
 ('table_named_null','SELECT * FROM IDENTIFIER(:tab)',{'tab':None}),
 ('table_unbound','SELECT * FROM IDENTIFIER(:tab)',None),
 ('scalar_named','SELECT IDENTIFIER(:col) AS value FROM input',{'col':'foo'}),
 ('scalar_positional','SELECT IDENTIFIER(?) AS value FROM input',['foo']),
 ('scalar_concat',"SELECT IDENTIFIER(concat('f','oo')) AS value FROM input",None),
 ('scalar_column','SELECT IDENTIFIER(foo) AS value FROM input',None),
 ('scalar_missing_column','SELECT IDENTIFIER(missing) AS value FROM input',None),
 ('scalar_subquery','SELECT IDENTIFIER((SELECT foo FROM input)) AS value FROM input',None),
 ('scalar_subquery_missing_column','SELECT IDENTIFIER((SELECT missing FROM input)) AS value FROM input',None),
 ('scalar_null','SELECT IDENTIFIER(CAST(NULL AS STRING)) AS value FROM input',None),
 ('scalar_integer','SELECT IDENTIFIER(1) AS value FROM input',None),
 ('scalar_unbound','SELECT IDENTIFIER(:col) AS value FROM input',None),
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
