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
tests=module('graph_tests',base/'test_lifecycle_errors.py')
execution=module('execution_tests',base/'test_execution.py')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[(op,lambda op=op:tests.test_missing_graph_has_structured_error(spark,op)) for op in ('define_output','define_flow','define_sql_graph_elements','start_run')]
cases += [('drop_missing',lambda:tests.test_dropping_missing_graph_is_idempotent(spark)),('drop_preserves_tables',lambda:execution.test_drop_graph_preserves_tables(spark,factory()))]
result={'spark_version':spark.version,'cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-graph-error-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==6 and all(c['outcome']=='passed' for c in result['cases'])
