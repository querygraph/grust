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
tests=module('registration_tests',base/'test_registration_errors.py')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
test_function=tests.test_duplicate_flows_preserve_identifiers_and_targets
grid=next(mark.args[1] for mark in test_function.pytestmark if mark.args[0]==('files','flow_name','targets'))
assert len(grid)==6
cases=[]
for param in grid:
 files,flow_name,targets=param.values
 for dry in (False,True):
  cases.append((f'{param.id},dry={dry}',lambda files=files,flow_name=flow_name,targets=targets,dry=dry:test_function(spark,factory(),root,files,flow_name,targets,dry)))
result={'spark_version':spark.version,'test_source_commit':'bbf438c0661cdfa4a3fab3af70439f7f788615d8','cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-duplicate-flow-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==12 and all(c['outcome']=='passed' for c in result['cases'])
