"""Observe public and SDP-file catalog phases on identical bare/wrapped inputs."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
import pyspark
OUT=Path(sys.argv[1]);ENGINE=sys.argv[2];assert ENGINE in ('spark','sail');OUT.mkdir(exist_ok=False)
def digest(p: Path) -> str:return hashlib.sha256(p.read_bytes()).hexdigest()
def listener() -> dict:
    p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
    assert p.returncode in (0,1)
    return {'exit_code':p.returncode,'stdout':p.stdout}
if ENGINE=='spark':assert listener()=={'exit_code':1,'stdout':''}
report={'engine':ENGINE,'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':digest(Path(__file__)),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'scope':'32 observed public/directive bare/wrapped registrations; no flow run or Scala-suite verdict','cases':[]}
spark=None
try:
    spark=(SparkSession.builder.remote('local[2]' if ENGINE=='spark' else 'sc://localhost:50094').appName('SDP catalog phases').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(OUT/'warehouse').as_uri()).getOrCreate())
    report['spark_version']=spark.version;assert spark.version=='4.2.1'
    report['installed_client_jars']={p.name:digest(p) for p in (Path(pyspark.__file__).parent/'jars').glob('spark-*4.2.1.jar') if any(k in p.name for k in ('pipelines','sql_','connect_'))}
    catalog=spark.catalog.currentCatalog();database=spark.catalog.currentDatabase();report['session_namespace']=[catalog,database]
    spark.conf.set('spark.sql.ansi.enabled','true')
    for site in ['public','directive']:
        for wrapped in [False,True]:
            for name,expr in [('current_catalog','current_catalog()'),('typeof_current','typeof(current_catalog())'),('rand','rand(0)'),('typeof_rand','typeof(rand(0))'),('generator',"explode(array('x'))"),('division','1 DIV 0'),('typeof_division','typeof(1 DIV 0)'),('assert_true','assert_true(true)')]:
                sql='SET CATALOG '+(f'IDENTIFIER({expr})' if wrapped else expr)
                case={'name':f'{site}_{"wrapped" if wrapped else "bare"}_{name}','site':site,'wrapped':wrapped,'query':sql};report['cases'].append(case)
                graph=None
                try:
                    if site=='public':case['rows']=[list(row) for row in spark.sql(sql).collect()]
                    else:
                        graph=create_dataflow_graph(spark,None,None,None)
                        SparkConnectGraphElementRegistry(spark,graph).register_sql(sql,OUT/'catalog.sql')
                    case['returned']=True
                except Exception as error:
                    case.update(returned=False,error=str(error),exception_type=type(error).__name__)
                    for method,key in [('getCondition','condition'),('getMessageParameters','parameters'),('getSqlState','sql_state')]:
                        try:case[key]=getattr(error,method)()
                        except Exception:case[key]=None
                finally:
                    if graph is not None:
                        command=pb.Command();command.pipeline_command.drop_dataflow_graph.dataflow_graph_id=graph;spark.client.execute_command(command)
                case['session_namespace']=[spark.catalog.currentCatalog(),spark.catalog.currentDatabase()]
                assert case['session_namespace']==[catalog,database]
finally:
    if spark is not None:spark.stop()
    report['listener_after_stop']=listener();report['completed_at']=datetime.now(timezone.utc).isoformat()
    (OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([{'name':c['name'],'returned':c['returned'],'condition':c.get('condition'),'error':c.get('error')} for c in report['cases']],indent=2))
