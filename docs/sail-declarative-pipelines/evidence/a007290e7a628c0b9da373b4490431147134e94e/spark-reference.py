import importlib.util,json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sail-sdp-spark-view-order-'))
spark=(SparkSession.builder.remote('local[2]').appName('Sail SDP view ordering reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate())
assert spark.version=='4.2.1'
source=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines/conftest.py')
spec=importlib.util.spec_from_file_location('pipeline_fixtures',source)
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[
 ('unselected_view','CREATE MATERIALIZED VIEW chosen AS SELECT 1 AS value; CREATE VIEW output AS SELECT 2 AS value;',{'refresh':['chosen']}),
 ('failed_table_write','CREATE MATERIALIZED VIEW raw(id BIGINT, missing STRING) AS SELECT * FROM range(2); CREATE VIEW output AS SELECT * FROM raw;',{}),
 ('selected_tables_via_view','CREATE MATERIALIZED VIEW raw AS SELECT * FROM range(1, 4); CREATE VIEW output AS SELECT * FROM raw; CREATE MATERIALIZED VIEW chosen AS SELECT sum(id) AS value FROM output;',{'refresh':['raw','chosen']}),
 ('view_with_absent_excluded_table','CREATE MATERIALIZED VIEW raw AS SELECT * FROM range(2); CREATE VIEW output AS SELECT * FROM raw; CREATE MATERIALIZED VIEW chosen AS SELECT 1 AS value;',{'refresh':['chosen']}),
 ('view_selected_alone','CREATE MATERIALIZED VIEW raw AS SELECT * FROM range(2); CREATE VIEW output AS SELECT * FROM raw;',{'refresh':['output']}),
]
results={'spark_version':spark.version,'cases':[]}
try:
    for name,sql,options in cases:
        for table in ('chosen','raw'):
            spark.sql('DROP TABLE IF EXISTS '+table)
        spark.sql('DROP VIEW IF EXISTS output')
        _,registry,run=factory()
        registry.register_sql(sql,Path(name+'.sql'))
        result={'name':name}
        try:
            run(**options)
            result['run']='success'
        except Exception as error:
            result['run']='failed';result['error_type']=type(error).__name__;result['error']=str(error)
        result['exists']={table:spark.catalog.tableExists(table) for table in ('chosen','raw','output')}
        for table,exists in result['exists'].items():
            if exists:
                try: result[table+'_rows']=[r.asDict() for r in spark.table(table).collect()]
                except Exception as error: result[table+'_read_error']=str(error)
        results['cases'].append(result)
finally:
    spark.stop()
Path('/tmp/sail-sdp-spark-view-order.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
