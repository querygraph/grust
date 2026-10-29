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
cases=[
 ('typed_case_sensitive',True,'CREATE TABLE output(id BIGINT, payload STRING) USING parquet PARTITIONED BY (ID BIGINT)', "INSERT INTO output (id, payload, ID) VALUES (1, 'a', 2)", 'SELECT id AS original, ID AS part FROM output'),
 ('by_name_insensitive',False,'CREATE TABLE output(id BIGINT) USING parquet', 'INSERT INTO output BY NAME SELECT CAST(7 AS BIGINT) AS ID', 'SELECT * FROM output'),
]
result={'spark_version':spark.version,'cases':[]}
try:
 for name,sensitive,ddl,insert,query in cases:
  spark.sql('DROP TABLE IF EXISTS output');spark.conf.set('spark.sql.caseSensitive',str(sensitive).lower())
  case={'name':name,'case_sensitive':sensitive,'ddl':ddl,'insert':insert,'query':query}
  try:
   spark.sql(ddl).collect();spark.sql(insert).collect();case['rows']=[r.asDict() for r in spark.sql(query).collect()];case['outcome']='success'
  except Exception as e:case.update(outcome='failed',error=str(e))
  result['cases'].append(case)
finally:spark.stop()
Path('/tmp/sail-sdp-write-case-reference-'+engine+'.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
