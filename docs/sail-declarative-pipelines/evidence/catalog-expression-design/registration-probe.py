from datetime import datetime,timezone
import argparse,json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.pipelines import spark_connect_pipeline as client
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['sail','spark']);args=parser.parse_args()
root=Path(tempfile.mkdtemp(prefix='sdp-catalog-registration-'))
builder=SparkSession.builder.remote('local[2]' if args.engine=='spark' else 'sc://localhost:50082').appName('catalog registration design')
if args.engine=='spark':builder=builder.config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri())
spark=builder.getOrCreate()
cat=spark.catalog.currentCatalog();db=spark.catalog.currentDatabase()
literal="'"+cat.replace("'","''")+"'"
cases=[('graph_default_false','true',"SET CATALOG CAST(CAST('not-an-int' AS INT) AS STRING)"),('graph_default_true','false',"SET CATALOG CAST(CAST('not-an-int' AS INT) AS STRING)"),('concat','true',f"SET CATALOG CONCAT({literal}, '')"),('cast','true',f"SET CATALOG CAST({literal} AS STRING)"),('unresolved','true',"SET CATALOG CONCAT(foo, '1')"),('multipart','true','SET CATALOG test.cat'),('wrong_type','true','SET CATALOG 1'),('null','true','SET CATALOG CAST(NULL AS STRING)'),('session_true_file_false','true',"SET spark.sql.ansi.enabled=false;\nSET CATALOG CAST(CAST('not-an-int' AS INT) AS STRING)"),('session_false_file_true','false',"SET spark.sql.ansi.enabled=true;\nSET CATALOG CAST(CAST('not-an-int' AS INT) AS STRING)"),('unset_database','true',f'SET CATALOG {literal}; CREATE MATERIALIZED VIEW unqualified_probe AS SELECT 1'),('explicit_database','true',f'SET CATALOG {literal}; CREATE MATERIALIZED VIEW `{db}`.qualified_probe AS SELECT 1'),('private_view','true',f'SET CATALOG {literal}; CREATE TEMPORARY VIEW private_probe AS SELECT 1')]
result={'recorded_at':datetime.now(timezone.utc).isoformat(),'engine':args.engine,'spark_version':spark.version,'catalog':cat,'database':db,'scope':'DefineSqlGraphElements registration only; fresh graph per case, no run/publication','cases':[]}
try:
    for name,ansi,sql in cases:
        spark.conf.set('spark.sql.ansi.enabled',ansi)
        graph_conf={'spark.sql.ansi.enabled':'false' if name=='graph_default_false' else 'true'} if name.startswith('graph_default_') else None
        graph_id=client.create_dataflow_graph(spark,None,None,graph_conf)
        registry=SparkConnectGraphElementRegistry(spark,graph_id)
        case={'name':name,'session_ansi':ansi,'graph_sql_conf':graph_conf,'sql':sql}
        try:
            registry.register_sql(sql,root/'catalog.sql')
            case['outcome']='registered'
        except Exception as error:
            case.update(outcome='rejected',exception_type=type(error).__name__,message=str(error))
            for method,key in [('getCondition','condition'),('getMessageParameters','parameters'),('getSqlState','sql_state')]:
                try:case[key]=getattr(error,method)()
                except Exception:pass
        finally:
            command=pb.Command();command.pipeline_command.drop_dataflow_graph.dataflow_graph_id=graph_id
            spark.client.execute_command(command)
        case['session_catalog_after']=spark.catalog.currentCatalog()
        case['session_database_after']=spark.catalog.currentDatabase()
        result['cases'].append(case)
finally:spark.stop()
Path('/tmp/sail-sdp-catalog-registration-'+args.engine+'.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps([{'name':c['name'],'outcome':c['outcome'],'condition':c.get('condition'),'parameters':c.get('parameters')} for c in result['cases']],indent=2,ensure_ascii=False))
assert result['spark_version']=='4.2.1'
assert all(c['session_catalog_after']==cat and c['session_database_after']==db for c in result['cases'])
