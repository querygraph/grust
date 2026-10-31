"""Observe Spark4.2.1's actual JVM schema duplicate validator."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql import types as T
import pyspark

OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False)
I=T.IntegerType()
def struct(*names):return T.StructType([T.StructField(name,I,True) for name in names])
mixed=struct('Foo','foo')
CASES=[
 ('root_insensitive',mixed,False),('root_sensitive',mixed,True),
 ('nested',T.StructType([T.StructField('outer',mixed,True)]),False),
 ('array',T.StructType([T.StructField('items',T.ArrayType(mixed),True)]),False),
 ('map_value',T.StructType([T.StructField('items',T.MapType(T.StringType(),mixed),True)]),False),
 ('root_before_nested',T.StructType([T.StructField('nested',mixed,True),T.StructField('Z',I),T.StructField('z',I)]),False),
 ('sorted_duplicate',struct('Z','z','A','a'),False),
 ('root_case_fold',struct('İ','i\u0307'),False),
 ('quoted_name',struct('A.B','a.b'),False),
 ('backtick_name',struct('A`B','a`b'),False),
 ('utf16_duplicate_order',struct('\ue000','\ue000','𐀀','𐀀'),True),
 ('case_sensitive_exact',struct('Foo','Foo'),True),
]
report={'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'actual JVM SchemaUtils validator; separate Parquet public runtime oracle required','cases':[]}
spark=None
try:
 spark=SparkSession.builder.master('local[1]').appName('schema validation reference').config('spark.ui.enabled','false').getOrCreate()
 report['spark_version']=spark.version;report['pyspark_version']=pyspark.__version__
 assert spark.version==pyspark.__version__=='4.2.1'
 for name,schema,sensitive in CASES:
  row={'name':name,'schema':schema.jsonValue(),'case_sensitive':sensitive}
  try:
   parsed=spark._jsparkSession.parseDataType(schema.json())
   spark._jvm.org.apache.spark.sql.util.SchemaUtils.checkSchemaColumnNameDuplication(parsed,sensitive)
   row['outcome']='success'
  except Exception as error:
   original=error.java_exception if hasattr(error,'java_exception') else error
   row.update(outcome='error',condition=original.getCondition(),sql_state=original.getSqlState(),parameters=dict(original.getMessageParameters()),message=str(original.getMessage()))
  report['cases'].append(row)
finally:
 if spark is not None:spark.stop()
 report['completed_at']=datetime.now(timezone.utc).isoformat()
 (OUT/'observations.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print('Recorded actual JVM validation cases:',len(report['cases']),flush=True)
