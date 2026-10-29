import importlib.util,json,os,sys,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
engine='sail'
root=Path(tempfile.mkdtemp(prefix='sail-sdp-properties-'))
builder=SparkSession.builder.remote('local[2]' if engine=='spark' else 'sc://localhost:50082').appName('SDP properties reference')
if engine=='spark': builder=builder.config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
spark=builder.getOrCreate()
if engine=='sail': spark.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
base=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines')
tests=module('orc_tests',base/'test_file_sources.py')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
report={'engine':'sail','spark_version':spark.version,'outcome':'unexpected-pass'}
try:
 try:tests.test_batch_pipeline_reads_file_source(spark,factory(),root,'orc')
 except Exception as error:report.update(outcome='unsupported',error_type=type(error).__name__,error=str(error))
finally:spark.stop()
Path('/tmp/sail-sdp-orc-gap.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['outcome']=='unsupported' and 'orc' in report['error'].lower()
