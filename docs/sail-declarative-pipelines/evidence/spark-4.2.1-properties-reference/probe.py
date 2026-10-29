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
source=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/conftest.py')
spec=importlib.util.spec_from_file_location('pipeline_fixtures',source)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
factory=f.pipeline_factory.__wrapped__(spark,root)
cases=[('unknown',{'pipelines.unknown':'x','custom':'keep'},False),('canonical',{'PIPELINES.RESET.ALLOWED':'false'},False),('invalid',{'pipelines.reset.allowed':'maybe'},False),('invalid_dry',{'pipelines.reset.allowed':'maybe'},True),('invalid_mixed_case',{'PIPELINES.RESET.ALLOWED':'maybe'},False),('trimmed',{'pipelines.reset.allowed':' TRUE '},False)]
result={'engine':engine,'spark_version':spark.version,'cases':[]}
try:
 for name,props,dry in cases:
    spark.sql('DROP TABLE IF EXISTS output')
    _,registry,run=factory()
    sql='CREATE MATERIALIZED VIEW output TBLPROPERTIES ('+', '.join("'"+k+"'='"+v+"'" for k,v in props.items())+') AS SELECT 1 AS value;'
    registry.register_sql(sql,Path(name+'.sql'))
    case={'name':name,'properties':props,'dry':dry}
    try:
        run(dry=dry);case['run']='success'
    except Exception as e:
        case.update(run='failed',error_type=type(e).__name__,error=str(e))
    case['exists']=spark.catalog.tableExists('output')
    if case['exists']:
        case['stored_properties']={r.key:r.value for r in spark.sql('SHOW TBLPROPERTIES output').collect() if r.key.lower().startswith('pipelines.') or r.key=='custom'}
    result['cases'].append(case)
finally:
 spark.stop()
Path('/tmp/sail-sdp-properties-'+engine+'.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
