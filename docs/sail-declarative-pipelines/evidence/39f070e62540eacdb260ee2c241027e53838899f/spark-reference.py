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
from pyspark.sql.connect import proto as pb
cases=[(f'sql,dry={dry}',lambda dry=dry:tests.test_sql_dataset_without_flow_has_structured_error(spark,factory(),root,dry)) for dry in (False,True)]
cases += [(f'kind={kind},dry={dry}',lambda kind=kind,dry=dry:tests.test_protocol_dataset_without_flow_preserves_identifier(spark,factory(),root,kind,dry)) for kind in (pb.TABLE,pb.MATERIALIZED_VIEW,pb.TEMPORARY_VIEW) for dry in (False,True)]
result={'spark_version':spark.version,'test_source_commit':'39f070e62540eacdb260ee2c241027e53838899f','cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-missing-producer-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==8 and all(c['outcome']=='passed' for c in result['cases'])
