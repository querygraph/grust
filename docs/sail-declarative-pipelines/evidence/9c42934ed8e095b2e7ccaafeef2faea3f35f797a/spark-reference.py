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
tests=module('file_tests',base/'test_file_sources.py')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[(f'file={fmt}',lambda fmt=fmt:tests.test_batch_pipeline_reads_file_source(spark,factory(),root,fmt)) for fmt in ('parquet','orc','json','csv')]
cases += [(f'empty_location={context}',lambda context=context:tests.test_empty_sql_file_location_is_rejected(spark,factory(),root,context)) for context in ('query','pipeline')]
result={'spark_version':spark.version,'test_source_commit':'9c42934ed8e095b2e7ccaafeef2faea3f35f797a','cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-file-sources-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==6 and all(c['outcome']=='passed' for c in result['cases'])
