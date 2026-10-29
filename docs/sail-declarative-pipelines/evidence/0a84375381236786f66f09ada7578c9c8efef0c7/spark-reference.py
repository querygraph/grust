import importlib.util,json,os,sys,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
engine=sys.argv[1]
root=Path(tempfile.mkdtemp(prefix='sail-sdp-properties-'))
builder=SparkSession.builder.remote('local[2]' if engine=='spark' else 'sc://localhost:50082').appName('SDP properties reference')
if engine=='spark': builder=builder.config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
spark=builder.getOrCreate()
if engine=='sail': spark.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
cases=[('typed_case_sensitive',True,'CREATE TABLE output(id BIGINT, payload STRING) USING parquet PARTITIONED BY (ID BIGINT)')]
result={'engine':engine,'spark_version':spark.version,'cases':[]}
try:
 for name,sensitive,sql in cases:
  spark.sql('DROP TABLE IF EXISTS output');spark.conf.set('spark.sql.caseSensitive',str(sensitive).lower())
  case={'name':name,'case_sensitive':sensitive,'sql':sql}
  try:
   spark.sql(sql).collect();case['outcome']='success'
  except Exception as e:case.update(outcome='failed',error_type=type(e).__name__,error=str(e),condition=e.getCondition() if hasattr(e,'getCondition') else None)
  case['exists']=spark.catalog.tableExists('output')
  if case['exists']:case['description']=[r.asDict() for r in spark.sql('DESCRIBE output').collect()];case['schema']=spark.table('output').schema.jsonValue()
  result['cases'].append(case)
finally:spark.stop()
Path('/tmp/sail-sdp-partition-scan-'+engine+'.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
