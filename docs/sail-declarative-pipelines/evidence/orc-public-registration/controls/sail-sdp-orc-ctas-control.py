"""Bounded original ORC CTAS and direct batch-MV assertions; no streaming/writer claim."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, tempfile, traceback, uuid
from pyspark.sql import SparkSession, Row, types as T
from pyspark.pipelines import spark_connect_pipeline as client
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.sql.connect import proto as pb

out=Path('/tmp/sail-sdp-orc-ctas-control.json'); assert not out.exists()
source=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/orc-source-design/spark-inputs/range/part-00000-74b0efde-68df-4650-b64c-a1581facdd5d-c000.zstd.orc')
source_hash='4e5c93a653db3bdd447775b059fc7f9c25f5ad4f66eb6d6d5c0596b89d04d5b8'
assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
server=json.loads(Path('/tmp/sail-sdp-orc-public/server.json').read_text())
assert server['outcome']=='running'
result={'started_at':datetime.now(timezone.utc).isoformat(),'server':server,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_pin':'617618396087429b5627a86ce933bb0f5d6645cb','source_test':'sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/SqlPipelineSuite.scala:434','source_file':str(source),'source_sha256':source_hash,'scope':'Original no-USING CTAS and direct batch MV output assertions using retained Spark-written RANGE fixture. No Sail ORC writer or streaming b execution.','cases':[]}
spark=SparkSession.builder.remote('sc://localhost:50088').getOrCreate()
result['spark_version']=spark.version
suffix=uuid.uuid4().hex; ctas='orc_ctas_'+suffix; mv='orc_mv_'+suffix; graph=None
temporary=tempfile.TemporaryDirectory(prefix='sdp-orc-ctas-')
try:
 root=Path(temporary.name)
 spark.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
 result['default_format']=spark.conf.get('spark.sql.sources.default'); assert result['default_format']=='parquet'
 expected_schema=T.StructType([T.StructField('id',T.LongType())])
 sql=f'CREATE TABLE {ctas} AS SELECT * FROM orc.`{source}`'
 result['ctas_sql']=sql; spark.sql(sql).collect()
 frame=spark.table(ctas); schema=frame.schema; rows=frame.collect()
 description=[list(row) for row in spark.sql('DESCRIBE EXTENDED '+ctas).collect()]
 result['cases'].append({'name':'ctas','schema':schema.jsonValue(),'rows':[list(row) for row in rows],'describe_extended':description})
 assert schema==expected_schema and set(rows)=={Row(0),Row(1),Row(2)}
 providers=[row[1] for row in description if row[0]=='Provider']; assert providers==['parquet'], providers
 graph=client.create_dataflow_graph(spark,None,None,None)
 reg=SparkConnectGraphElementRegistry(spark,graph)
 sql=f'CREATE MATERIALIZED VIEW {mv} AS SELECT * FROM orc.`{source}`'
 result['mv_sql']=sql; reg.register_sql(sql,root/'pipeline.sql')
 client.handle_pipeline_events(client.start_run(spark,graph,None,False,None,False,(root/'state').as_uri()))
 frame=spark.table(mv); schema=frame.schema; rows=frame.collect()
 result['cases'].append({'name':'batch_mv','schema':schema.jsonValue(),'rows':[list(row) for row in rows]})
 assert schema==expected_schema and set(rows)=={Row(0),Row(1),Row(2)}
 result['outcome']='passed'
except BaseException:
 result['outcome']='failed'; result['error']=traceback.format_exc()
finally:
 cleanup_errors=[]
 if graph:
  try:
   command=pb.Command(); command.pipeline_command.drop_dataflow_graph.dataflow_graph_id=graph; spark.client.execute_command(command)
  except BaseException:
   cleanup_errors.append({'action':'drop_graph','error':traceback.format_exc()})
 for name in (ctas,mv):
  try:
   spark.sql('DROP TABLE IF EXISTS '+name).collect()
  except BaseException:
   cleanup_errors.append({'action':'drop_table','table':name,'error':traceback.format_exc()})
 try:
  result['tables_absent']=all(not spark.catalog.tableExists(name) for name in (ctas,mv))
  assert result['tables_absent']
 except BaseException:
  cleanup_errors.append({'action':'verify_tables_absent','error':traceback.format_exc()})
 try:
  result['source_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
  assert result['source_unchanged']
 except BaseException:
  cleanup_errors.append({'action':'verify_source_unchanged','error':traceback.format_exc()})
 for name,action in [('session_stop',spark.stop),('temporary_cleanup',temporary.cleanup)]:
  try:
   action()
  except BaseException:
   cleanup_errors.append({'action':name,'error':traceback.format_exc()})
 result['cleanup_errors']=cleanup_errors
 if cleanup_errors:
  result['outcome']='failed'
 result['completed_at']=datetime.now(timezone.utc).isoformat()
 out.write_text(json.dumps(result,indent=2)+'\n')
assert result['outcome']=='passed', result
print('PASS original ORC CTAS and direct batch MV rows/schema on '+server['sail_commit'])
