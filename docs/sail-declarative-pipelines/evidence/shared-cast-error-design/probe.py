from datetime import datetime,timezone
from pathlib import Path
import argparse,json,os
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
 os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['spark','sail']);args=parser.parse_args()
s=SparkSession.builder.remote('local[2]' if args.engine=='spark' else 'sc://localhost:50082').getOrCreate()
cases=[]
for name,target,value in [('int','INT','bad'),('integer_alias','INTEGER','bad'),('tinyint','TINYINT','bad'),('smallint','SMALLINT','bad'),('bigint','BIGINT','bad'),('float','FLOAT','bad'),('double','DOUBLE','bad'),('decimal','DECIMAL(8,2)','bad'),('boolean','BOOLEAN','bad'),('date','DATE','bad'),('timestamp','TIMESTAMP','bad'),('int_overflow','INT','2147483648'),('decimal_overflow','DECIMAL(3,1)','123456'),('quote','INT',"a'b"),('newline','INT','a\nb')]:
 literal="'"+value.replace('\\','\\\\').replace("'","\\'").replace('\n','\\n')+"'"
 cases.append((name,'true',f'SELECT CAST({literal} AS {target}) AS value'))
cases += [('array_row','true',"SELECT CAST(value AS INT) AS result FROM VALUES ('1'), ('bad'), ('2') AS t(value)"),('nested','true',"SELECT CAST(CAST('bad' AS INT) AS STRING) AS value"),('try_nested','true',"SELECT TRY_CAST(CAST('bad' AS INT) AS STRING) AS value"),('try_int','true',"SELECT TRY_CAST('bad' AS INT) AS value"),('legacy_int','false',"SELECT CAST('bad' AS INT) AS value"),('null','true',"SELECT CAST(CAST(NULL AS STRING) AS INT) AS value"),('valid','true',"SELECT CAST('12' AS INT) AS value"),('numeric_overflow','true',"SELECT CAST(1000L AS TINYINT) AS value"),('row_null','true',"SELECT CAST(value AS INT) AS result FROM VALUES (CAST(NULL AS STRING)), ('bad') AS t(value)")]
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'engine':args.engine,'spark_version':s.version,'cases':[]}
try:
 for name,ansi,sql in cases:
  s.conf.set('spark.sql.ansi.enabled',ansi);c={'name':name,'ansi':ansi,'sql':sql}
  try:c.update(outcome='accepted',rows=[list(row) for row in s.sql(sql).collect()])
  except Exception as error:
   c.update(outcome='rejected',exception_type=type(error).__name__,condition=error.getCondition(),sql_state=error.getSqlState(),parameters=error.getMessageParameters(),message=str(error))
  r['cases'].append(c)
finally:s.stop()
Path('/tmp/sail-sdp-cast-design-'+args.engine+'.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps([{k:v for k,v in c.items() if k not in ('message','sql')} for c in r['cases']],indent=2))
assert r['spark_version']=='4.2.1' and len(r['cases'])==24
