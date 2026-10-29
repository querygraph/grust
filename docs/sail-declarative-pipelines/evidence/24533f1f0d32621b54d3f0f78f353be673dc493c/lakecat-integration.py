from pathlib import Path
import importlib.util,json,subprocess,traceback
from pyspark.sql import SparkSession
c=json.loads(Path('/tmp/sail-sdp-lakecat-integration.json').read_text())
root=Path(c['root'])
spark=SparkSession.builder.remote(c['spark_remote']).getOrCreate()
spark.conf.set('spark.sql.warehouse.dir',c['warehouse'])
spec=importlib.util.spec_from_file_location('pipeline_fixtures','/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/conftest.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
factory=f.pipeline_factory.__wrapped__(spark,root)
r={'sail_commit':subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','rev-parse','HEAD'],text=True).strip(),'lakecat_commit':subprocess.check_output(['git','-C','/Users/alexy/src/lakecat-sdp-gate','rev-parse','HEAD'],text=True).strip(),'spark_version':spark.version,'cases':[]}
cases=[
 ('initial','CREATE MATERIALIZED VIEW output USING iceberg AS SELECT id AS value FROM range(3);',[0,1,2]),
 ('refresh','CREATE MATERIALIZED VIEW output USING iceberg AS SELECT id AS value FROM range(2,4);',[2,3]),
 ('column_comment',"CREATE MATERIALIZED VIEW output(value BIGINT COMMENT 'refreshed') USING iceberg AS SELECT id AS value FROM range(4,5);",[4]),
 ('replace_columns',"CREATE MATERIALIZED VIEW output USING iceberg AS SELECT 'new' AS other;",['new']),
]
try:
 for name,sql,expected in cases:
  case={'name':name,'sql':sql}
  try:
   _,registry,run=factory();registry.register_sql(sql,Path(name+'.sql'));run()
   df=spark.table('output');rows=[row[0] for row in df.collect()];assert sorted(rows)==expected,(rows,expected)
   case.update(outcome='passed',rows=rows,schema=df.schema.jsonValue())
   if name=='column_comment':assert df.schema['value'].metadata['comment']=='refreshed'
  except Exception as error:
   case.update(outcome='failed',error_type=type(error).__name__,error=str(error));r['cases'].append(case);break
  r['cases'].append(case)
finally:
 spark.stop()
Path('/tmp/sail-sdp-lakecat-integration-result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
assert len(r['cases'])==4 and all(x['outcome']=='passed' for x in r['cases'])
