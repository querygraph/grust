from datetime import datetime,timezone
import hashlib,importlib.util,json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
 os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sdp-catalog-activation-reference-'))
spark=SparkSession.builder.remote('local[2]').appName('Catalog expression reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
base=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines')
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
tests=module('catalog_tests',base/'test_catalog_expressions.py');fixtures=module('catalog_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
result={'recorded_at':datetime.now(timezone.utc).isoformat(),'spark_version':spark.version,'test_source_sha256':hashlib.sha256((base/'test_catalog_expressions.py').read_bytes()).hexdigest(),'fixture':'warehouse configured on builder; invokes unchanged public test functions','cases':[]}
try:
 for expr in ["CONCAT({catalog}, '')",'CAST({catalog} AS STRING)']:
  for kind in ['ordinary','pipeline']:
   try:
    if kind=='ordinary':tests.test_catalog_expression_in_ordinary_sql(spark,expr)
    else:tests.test_catalog_expression_publishes_pipeline_output(spark,factory(),root,expr)
    result['cases'].append({'name':kind+': '+expr,'outcome':'passed'})
   except Exception as error:result['cases'].append({'name':kind+': '+expr,'outcome':'failed','error':repr(error)})
 for expr in ["CONCAT(foo, '1')",'test.cat','1','CAST(NULL AS STRING)']:
  try:
   tests.test_invalid_catalog_expression_has_native_pipeline_diagnostics(spark,factory(),root,expr)
   result['cases'].append({'name':'invalid: '+expr,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':'invalid: '+expr,'outcome':'failed','error':repr(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-catalog-activation-reference.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
assert result['spark_version']=='4.2.1' and len(result['cases'])==8 and all(c['outcome']=='passed' for c in result['cases']),result
