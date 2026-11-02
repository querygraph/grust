"""Observe namespace policy for early and late SDP identifiers."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph,start_run
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);ENGINE=sys.argv[2]
assert ENGINE in ('spark','sail')
def define(spark,graph,name,query,table):
 c=pb.Command();c.pipeline_command.define_output.CopyFrom(pb.PipelineCommand.DefineOutput(dataflow_graph_id=graph,output_name=name,output_type=pb.OutputType.MATERIALIZED_VIEW if table else pb.OutputType.TEMPORARY_VIEW,table_details=pb.PipelineCommand.DefineOutput.TableDetails(format='parquet') if table else None));spark.client.execute_command(c)
 r=pb.Relation();r.sql.query=query;c=pb.Command();c.pipeline_command.define_flow.CopyFrom(pb.PipelineCommand.DefineFlow(dataflow_graph_id=graph,flow_name=name,target_dataset_name=name,relation_flow_details=pb.PipelineCommand.DefineFlow.WriteRelationFlowDetails(relation=r)));spark.client.execute_command(c)
report={'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Public namespace phase oracle; rows and session namespace only, no full metadata or Scala verdict','engine':ENGINE,'cases':[]};spark=None
try:
 spark=SparkSession.builder.remote('local[1]' if ENGINE=='spark' else 'sc://localhost:50094').appName('computed namespace').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(OUT/'warehouse').as_uri()).getOrCreate();report['spark_version']=spark.version;assert ENGINE!='spark' or spark.version=='4.2.1'
 for ns,value in [('binding_a',9),('binding_b',10)]:
  spark.sql('CREATE DATABASE '+ns).collect();spark.sql('USE '+ns).collect();spark.sql('CREATE TABLE external_input USING parquet AS SELECT '+str(value)+' AS foo').collect()
 for name,query in [('named','SELECT foo FROM external_input'),('literal',"SELECT foo FROM IDENTIFIER('external_input')"),('computed',"SELECT foo FROM IDENTIFIER(concat('external_', 'input'))")]:
  spark.sql('USE binding_a').collect();graph=create_dataflow_graph(spark,spark.catalog.currentCatalog(),'binding_a',None);define(spark,graph,'result_'+name,query,True);spark.sql('USE binding_b').collect()
  row={'name':name,'query':query,'events':[]};report['cases'].append(row)
  try:
   for event in start_run(spark,graph,None,False,None,False,(OUT/name/'state').as_uri()):
    if 'pipeline_event_result' in event:row['events'].append(event['pipeline_event_result'].event.message)
   row['returned']=True
  except Exception as error:row.update(returned=False,error=str(error))
  row['rows']=[r.asDict() for r in spark.table('binding_a.result_'+name).collect()]
  row['session_namespace']=spark.catalog.currentDatabase()
finally:
 if spark is not None:spark.stop()
 report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
