import importlib.util,json,os,sys,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
engine='spark'
root=Path(tempfile.mkdtemp(prefix='sail-sdp-properties-'))
builder=SparkSession.builder.remote('local[2]' if engine=='spark' else 'sc://localhost:50082').appName('SDP properties reference')
if engine=='spark': builder=builder.config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
spark=builder.getOrCreate()
if engine=='sail': spark.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
base=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines')
tests=module('basic_sql_tests',base/'test_sql_batch.py')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[(name,lambda name=name:getattr(tests,name)(spark,factory(),root)) for name in ('test_static_sql_dataset','test_escaped_hyphenated_dataset_resolution','test_persisted_view_dependency_chain','test_sql_aggregation_over_pipeline_dataset','test_sql_join_over_private_views')]
result={'spark_version':spark.version,'test_source_commit':'efc21f2c53b0d8c886b31928ed67131a1de7c6db','cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-sql-basic-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==5 and all(c['outcome']=='passed' for c in result['cases'])
