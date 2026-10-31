"""Observe WithRelations registration and run phases through public SDP commands."""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,json,os,subprocess,sys
for k in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph,start_run
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False)
CASE='spark.sql.caseSensitive'
def read(name):
 r=pb.Relation();r.read.named_table.unparsed_identifier=name;return r
def command(spark,graph,name,relation,conf,table=False):
 c=pb.Command();c.pipeline_command.define_output.CopyFrom(pb.PipelineCommand.DefineOutput(dataflow_graph_id=graph,output_name=name,output_type=pb.OutputType.MATERIALIZED_VIEW if table else pb.OutputType.TEMPORARY_VIEW,table_details=pb.PipelineCommand.DefineOutput.TableDetails(format='parquet') if table else None));spark.client.execute_command(c)
 c=pb.Command();c.pipeline_command.define_flow.CopyFrom(pb.PipelineCommand.DefineFlow(dataflow_graph_id=graph,flow_name=name,target_dataset_name=name,sql_conf=conf,relation_flow_details=pb.PipelineCommand.DefineFlow.WriteRelationFlowDetails(relation=relation)));spark.client.execute_command(c)
def sql(text):
 r=pb.Relation();r.sql.query=text;return r
def relation(kind):
 r=pb.Relation();wr=r.with_relations
 ref=read('external_input' if kind=='parameter_external' else 'z_sensitive');ref.common.plan_id=42
 if kind.startswith('parameter'):
  alias=pb.Relation();alias.common.plan_id=42;alias.subquery_alias.alias='param';alias.subquery_alias.input.CopyFrom(ref)
  wr.root.CopyFrom(sql('SELECT Foo FROM param'));wr.references.append(alias)
 else:
  wr.root.project.input.CopyFrom(read('a_insensitive'))
  value=wr.root.project.expressions.add();value.alias.name.append('value');value.alias.expr.unresolved_attribute.unparsed_identifier='Bar'
  if kind in ('scalar_used','scalar_nested'):
   scalar=wr.root.project.expressions.add();scalar.alias.name.append('scalar_value')
   sub=scalar.alias.expr if kind=='scalar_used' else scalar.alias.expr.unresolved_function.arguments.add()
   if kind=='scalar_nested':scalar.alias.expr.unresolved_function.function_name='abs'
   sub.subquery_expression.plan_id=42;sub.subquery_expression.subquery_type=pb.SubqueryExpression.SUBQUERY_TYPE_SCALAR
  if kind=='unused_alias':
   alias=pb.Relation();alias.common.plan_id=42;alias.subquery_alias.alias='unused';alias.subquery_alias.input.CopyFrom(ref);ref=alias
  wr.references.append(ref)
 return r
report={'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'Spark only, public protobuf registration versus run phases; not Sail or Scala acceptance','cases':[]}
spark=None
try:
 check=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert check.returncode==1 and not check.stdout
 spark=SparkSession.builder.remote('local[1]').appName('SDP relation reference phases').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(OUT/'warehouse').as_uri()).getOrCreate();report['spark_version']=spark.version;assert spark.version=='4.2.1'
 for i,kind in enumerate(['scalar_used','scalar_nested','scalar_unused','unused_alias','parameter_local','parameter_external']):
  row={'name':kind};report['cases'].append(row)
  namespace='relref_'+str(i);spark.sql('CREATE DATABASE '+namespace).collect();spark.sql('USE '+namespace).collect();spark.sql('CREATE TABLE external_input USING parquet AS SELECT 9 AS foo').collect()
  graph=create_dataflow_graph(spark,spark.catalog.currentCatalog(),namespace,None)
  command(spark,graph,'z_sensitive',sql('SELECT 1 AS foo'),{CASE:'true'})
  command(spark,graph,'a_insensitive',sql('SELECT 2 AS bar'),{CASE:'false'})
  root=relation(kind);row['relation_base64']=base64.b64encode(root.SerializeToString(deterministic=True)).decode()
  try:command(spark,graph,'result',root,{},table=True);row['registered']=True
  except Exception as error:row.update(registered=False,registration_error=str(error),registration_condition=error.getCondition(),registration_state=error.getSqlState());continue
  row['events']=[]
  try:
   for event in start_run(spark,graph,None,False,None,False,(OUT/kind/'state').as_uri()):
    if 'pipeline_event_result' in event:row['events'].append(event['pipeline_event_result'].event.message)
   row['run_returned']=True
  except Exception as error:row.update(run_returned=False,run_error=str(error))
  row['result_exists']=spark.catalog.tableExists('result')
  if row['result_exists']:row['rows']=[r.asDict() for r in spark.table('result').collect()]
finally:
 if spark is not None:spark.stop()
 check=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);report['listener_after_stop']={'exit_code':check.returncode,'stdout':check.stdout}
 report['completed_at']=datetime.now(timezone.utc).isoformat();(OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded relation phase cases',len(report['cases']),flush=True)
