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
source=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/conftest.py')
spec=importlib.util.spec_from_file_location('pipeline_fixtures',source)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
factory=f.pipeline_factory.__wrapped__(spark,root)
result={'engine':engine,'spark_version':spark.version,'sql':'CREATE VIEW pv2 AS SELECT * FROM pv1; CREATE VIEW pv1 AS SELECT 1 + 1;'}
try:
 _,registry,run=factory();registry.register_sql(result['sql'],Path('failed_view.sql'))
 try:run();result['run']='success'
 except Exception as e:result.update(run='failed',error_type=type(e).__name__,error=str(e))
 result['published']={name:spark.catalog.tableExists(name) for name in ('pv1','pv2')}
finally:spark.stop()
Path('/tmp/sail-sdp-failed-view-before.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
