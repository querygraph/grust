import importlib.util,json,os,sys,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
engine=sys.argv[1]
root=Path(tempfile.mkdtemp(prefix='sail-sdp-properties-'))
builder=SparkSession.builder.remote('local[2]' if engine=='spark' else 'sc://localhost:50082').appName('SDP properties reference')
if engine=='spark': builder=builder.config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
spark=builder.getOrCreate()
if engine=='sail': spark.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
base=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines')
fixtures=module('graph_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
catalog=spark.catalog.currentCatalog();database=spark.catalog.currentDatabase()
from pyspark.pipelines.spark_connect_pipeline import start_run,handle_pipeline_events
from uuid import uuid4
prefix='scope_'+uuid4().hex[:10]
input_name=prefix+'_input'
spark.sql(f'CREATE TABLE {input_name} AS SELECT 7 AS value')
cases=[('unqualified_create',[f'SET CATALOG {catalog}; CREATE MATERIALIZED VIEW {prefix}_unqualified AS SELECT 7 AS value'],prefix+'_unqualified'),('two_part_create',[f'SET CATALOG {catalog}; CREATE MATERIALIZED VIEW {database}.{prefix}_two AS SELECT 7 AS value'],database+'.'+prefix+'_two'),('use_after_set',[f'SET CATALOG {catalog}; USE DATABASE {database}; CREATE MATERIALIZED VIEW {prefix}_use AS SELECT 7 AS value'],prefix+'_use'),('file_reset',[f'SET CATALOG {catalog}',f'CREATE MATERIALIZED VIEW {prefix}_reset AS SELECT 7 AS value'],prefix+'_reset'),('temporary_after_set',[f'SET CATALOG {catalog}; CREATE TEMPORARY VIEW intermediate AS SELECT 7 AS value; USE DATABASE {database}; CREATE MATERIALIZED VIEW {prefix}_private AS SELECT * FROM intermediate'],prefix+'_private'),('unqualified_external_read',[f'SET CATALOG {catalog}; CREATE MATERIALIZED VIEW {database}.{prefix}_read AS SELECT * FROM {input_name}'],database+'.'+prefix+'_read'),('invalid_catalog_expression',["SET CATALOG CONCAT(foo, '1')"],None),('multipart_catalog_expression',['SET CATALOG test.cat'],None),('constant_catalog_expression',[f"SET CATALOG CONCAT('{catalog[:1]}', '{catalog[1:]}'); USE DATABASE {database}; CREATE MATERIALIZED VIEW {prefix}_constant AS SELECT 7 AS value"],prefix+'_constant')]
report={'engine':engine,'spark_version':spark.version,'catalog':catalog,'database':database,'cases':[]}
try:
 for name,sql_files,output in cases:
  graph_id,registry,run=factory();item={'name':name,'sql_files':sql_files,'stage':'register'}
  try:
   for index,sql in enumerate(sql_files):registry.register_sql(sql,root/f'{name}-{index}.sql')
   item['registration']='passed'
   if output:
    item['stage']='run';run();item['run']='passed';item['stage']='read';item['rows']=[tuple(row) for row in spark.table(output).collect()]
   item['outcome']='passed'
  except Exception as error:
   item.update(outcome='failed',error_type=type(error).__name__,error=str(error))
   for method,key in [('getCondition','condition'),('getSqlState','sql_state'),('getMessageParameters','parameters')]:
    if hasattr(error,method):item[key]=getattr(error,method)()
  report['cases'].append(item)
finally:spark.stop()
Path('/tmp/sail-sdp-catalog-scope-'+engine+'.json').write_text(json.dumps(report,indent=2)+'\n')
