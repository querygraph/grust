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
tests=module('protocol_tests',base/'test_protocol_identifiers.py')
from pyspark.sql.connect import proto as pb
cases=[]
for kind,name,database in [(pb.MATERIALIZED_VIEW,'`mv`',None),(pb.TEMPORARY_VIEW,'tv',None),(pb.MATERIALIZED_VIEW,'mv','custom_db'),(pb.TEMPORARY_VIEW,'tv','custom_db')]:
 cases.append((f'flow={kind},name={name},database={database}',lambda kind=kind,name=name,database=database:tests.test_define_flow_returns_resolved_identifier(spark,kind,name,database)))
api=module('api_tests',base.parent/'dataframe/test_table_function.py')
for values in (None,[],[2,5]):
 cases.append((f'api_values={values}',lambda values=values:api.test_connect_table_function_relation(spark,values)))
result={'spark_version':spark.version,'test_source_commit':'f064fb2709e14d3064c93a9c03b25dbcd8d40ec5','cases':[]}
try:
 for name,call in cases:
  try:call();result['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:result['cases'].append({'name':name,'outcome':'failed','error':str(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-table-function-reference.json').write_text(json.dumps(result,indent=2)+'\n')
assert len(result['cases'])==7 and all(c['outcome']=='passed' for c in result['cases'])
