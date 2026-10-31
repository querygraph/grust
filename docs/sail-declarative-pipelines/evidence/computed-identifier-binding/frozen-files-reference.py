"""Observe file-set versus content freezing for SQLWithRefs parameters."""
from pathlib import Path
from datetime import datetime, timezone
import base64,hashlib,json,os,subprocess,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph,start_run
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def owners():
 r=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);return {'exit_code':r.returncode,'stdout':r.stdout}
def define(spark,graph,root):
 c=pb.Command();c.pipeline_command.define_output.CopyFrom(pb.PipelineCommand.DefineOutput(dataflow_graph_id=graph,output_name='result',output_type=pb.OutputType.MATERIALIZED_VIEW,table_details=pb.PipelineCommand.DefineOutput.TableDetails(format='parquet')));spark.client.execute_command(c)
 c=pb.Command();c.pipeline_command.define_flow.CopyFrom(pb.PipelineCommand.DefineFlow(dataflow_graph_id=graph,flow_name='result',target_dataset_name='result',relation_flow_details=pb.PipelineCommand.DefineFlow.WriteRelationFlowDetails(relation=root)));spark.client.execute_command(c)
report={'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':sha(Path(__file__)),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'Spark SQLWithRefs public registration/run file-mutation observations; no Sail verdict','cases':[]};spark=None
try:
 assert owners()=={'exit_code':1,'stdout':''}
 spark=SparkSession.builder.remote('local[1]').appName('frozen parameter files').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(OUT/'warehouse').as_uri()).getOrCreate();report['spark_version']=spark.version;assert spark.version=='4.2.1'
 for kind in ('append','delete','replace'):
  ns='frozen_files_'+kind;spark.sql('CREATE DATABASE '+ns).collect();spark.sql('USE '+ns).collect()
  location=OUT/kind/'source';location.mkdir(parents=True)
  source=location/'original.parquet';pq.write_table(pa.table({'foo':pa.array([9],type=pa.int32())}),source)
  spark.sql("CREATE TABLE external_input USING parquet LOCATION '"+location.as_uri()+"'").collect()
  graph=create_dataflow_graph(spark,spark.catalog.currentCatalog(),ns,None)
  root=pb.Relation();root.with_relations.root.sql.query='SELECT v FROM param'
  alias=root.with_relations.references.add();alias.common.plan_id=42;alias.subquery_alias.alias='param';alias.subquery_alias.input.sql.query='SELECT foo + 1 AS v FROM external_input'
  row={'name':kind,'relation_base64':base64.b64encode(root.SerializeToString(deterministic=True)).decode(),'files_at_registration':{p.name:sha(p) for p in location.glob('*.parquet')}};report['cases'].append(row)
  define(spark,graph,root);row['registered']=True
  if kind=='append':pq.write_table(pa.table({'foo':pa.array([10],type=pa.int32())}),location/'added.parquet')
  elif kind=='delete':source.unlink()
  else:pq.write_table(pa.table({'foo':pa.array([11],type=pa.int32())}),source)
  row['files_at_run']={p.name:sha(p) for p in location.glob('*.parquet')}
  if kind!='delete':row['fresh_path_rows']=sorted([r.asDict() for r in spark.read.parquet(location.as_uri()).collect()],key=lambda x:x['foo'])
  row['events']=[]
  try:
   for event in start_run(spark,graph,None,False,None,False,(OUT/kind/'state').as_uri()):
    if 'pipeline_event_result' in event:row['events'].append(event['pipeline_event_result'].event.message)
   row['run_returned']=True
  except Exception as error:row.update(run_returned=False,run_error=str(error),exception_type=type(error).__name__)
  row['result_exists']=spark.catalog.tableExists('result')
  if row['result_exists']:row['rows']=[r.asDict() for r in spark.table('result').collect()]
finally:
 if spark is not None:spark.stop()
 report['listener_after_stop']=owners();report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
print('Frozen parameter file-mutation observations recorded',flush=True)
