import json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph,handle_pipeline_events,start_run
root=Path(tempfile.mkdtemp(prefix='sail-sdp-spark-materialization-'))
spark=(SparkSession.builder.remote('local[2]').appName('Sail SDP materialization reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate())
results={'spark_version':spark.version,'cases':[]}
try:
    for name,sql,tables in [
        ('unknown_format','CREATE MATERIALIZED VIEW a_valid AS SELECT * FROM range(2); CREATE MATERIALIZED VIEW z_invalid USING missing_format AS SELECT * FROM a_valid;', ['a_valid','z_invalid']),
        ('declared_order',"CREATE MATERIALIZED VIEW ordered (second BIGINT COMMENT 'two', first BIGINT COMMENT 'one') AS SELECT id AS first, id+10 AS second FROM range(2)",['ordered']),
        ('inferred_nested',"CREATE MATERIALIZED VIEW nested AS SELECT named_struct('id',id) AS value FROM range(1)",['nested']),
    ]:
        graph=create_dataflow_graph(spark,None,None,None)
        registry=SparkConnectGraphElementRegistry(spark,graph)
        registry.register_sql(sql,Path(name+'.sql'))
        try:
            handle_pipeline_events(start_run(spark,graph,None,False,None,False,(root/name).as_uri()))
            case={'name':name,'outcome':'success'}
        except Exception as error:
            case={'name':name,'outcome':'error','type':type(error).__name__,'condition':error.getCondition(),'message':str(error)}
        case['tables']={}
        for table in tables:
            info={'exists':spark.catalog.tableExists(table)}
            if info['exists']:
                info['schema']=spark.table(table).schema.jsonValue()
                info['rows']=[row.asDict(recursive=True) for row in spark.table(table).collect()]
            case['tables'][table]=info
        results['cases'].append(case)
finally:
    spark.stop()
Path('/tmp/sail-sdp-spark-materialization-reference.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
