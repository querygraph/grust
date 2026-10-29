from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,tempfile
from pyspark.sql import SparkSession
from pyspark.pipelines import spark_connect_pipeline as client
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.sql.connect import proto as pb
root=Path(tempfile.mkdtemp(prefix='sdp-orc-sail-'));s=SparkSession.builder.remote('sc://localhost:50082').getOrCreate();s.conf.set('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'sail_commit':'8d044db3860b4f55e49543c833246af31e986e2e','cli_sha256':hashlib.sha256(Path('/Users/alexy/src/sail-sdp-gate/target/debug/sail').read_bytes()).hexdigest(),'server_spark_version':s.version,'cases':[]}
source='/tmp/sail-sdp-orc-reference/data/range'
try:
 for name in ['write_default','read_spark_file','ctas','pipeline_batch']:
  graph=None
  try:
   if name=='write_default':s.range(3).write.format('orc').mode('overwrite').save(str(root/'written'))
   elif name=='read_spark_file':s.read.orc(source).collect()
   elif name=='ctas':s.sql(f'CREATE TABLE orc_external AS SELECT * FROM orc.`{source}`').collect()
   else:
    graph=client.create_dataflow_graph(s,None,None,None);reg=SparkConnectGraphElementRegistry(s,graph)
    reg.register_sql(f'CREATE MATERIALIZED VIEW orc_batch AS SELECT * FROM orc.`{source}`',root/'pipeline.sql')
    client.handle_pipeline_events(client.start_run(s,graph,None,False,None,False,(root/'state').as_uri()))
   r['cases'].append({'name':name,'outcome':'passed'})
  except Exception as e:r['cases'].append({'name':name,'outcome':'failed','error_type':type(e).__name__,'error':str(e)})
  finally:
   if graph:
    cmd=pb.Command();cmd.pipeline_command.drop_dataflow_graph.dataflow_graph_id=graph;s.client.execute_command(cmd)
finally:
 for name in ['orc_external','orc_batch']:s.sql(f'DROP TABLE IF EXISTS {name}').collect()
 s.stop()
Path('/tmp/sail-sdp-orc-sail-baseline.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
