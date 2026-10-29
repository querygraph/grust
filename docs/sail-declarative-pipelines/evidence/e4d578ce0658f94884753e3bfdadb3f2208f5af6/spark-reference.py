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
source=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/conftest.py')
spec=importlib.util.spec_from_file_location('pipeline_fixtures',source)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
factory=f.pipeline_factory.__wrapped__(spark,root)
spec=importlib.util.spec_from_file_location('property_tests','/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines/test_properties.py')
tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
result={'spark_version':spark.version,'cases':[]}
try:
 for i,values in enumerate(tests.test_pipeline_table_properties.pytestmark[0].args[1]):
    spark.sql('DROP TABLE IF EXISTS output')
    try:
        tests.test_pipeline_table_properties(spark,factory(),*values)
        result['cases'].append({'case':i,'outcome':'passed'})
    except Exception as e:
        result['cases'].append({'case':i,'outcome':'failed','error':str(e)})
finally:
 spark.stop()
Path('/tmp/sail-sdp-properties-api-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==6 and all(c['outcome']=='passed' for c in result['cases'])
