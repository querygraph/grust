import hashlib,importlib.util,json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
 os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sdp-origin-reference-'))
spark=SparkSession.builder.remote('local[2]').appName('SQL statement origin reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
base=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines')
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
tests=module('origin_tests',base/'test_sql_origins.py');fixtures=module('origin_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[('leading-trivia',"-- 雪\nSELECT 'é;雪' /* trailing ; */;","SELECT 'é;雪' /* trailing ; */",2),('second-statement',"SET marker = 1;\n\n-- source\nSELECT 2 -- trailing\n;","SELECT 2 -- trailing\n",4)]
result={'spark_version':spark.version,'test_source_sha256':hashlib.sha256((base/'test_sql_origins.py').read_bytes()).hexdigest(),'cases':[]}
try:
 for name,sql,offending,line in cases:
  try:
   tests.test_sql_registration_error_retains_statement_origin(factory(),root,sql,offending,line)
   result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':repr(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-registration-origins-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert result['spark_version']=='4.2.1' and all(c['outcome']=='passed' for c in result['cases']),result
