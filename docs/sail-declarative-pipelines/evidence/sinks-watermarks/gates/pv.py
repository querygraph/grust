import os, sys
from pathlib import Path
from pyspark.sql import SparkSession
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
s=SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir',(out/'wh').as_uri()).getOrCreate()
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry as Reg
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run
def run(name, sql):
    g=create_dataflow_graph(s,'spark_catalog','default',None); r=Reg(s,g); r.register_sql(sql,Path('p.sql')); ev=[]
    try:
        for it in start_run(s,g,None,False,None,False,(out/name).as_uri()):
            if 'pipeline_event_result' in it: ev.append(it['pipeline_event_result'].event.message[:240])
        o='ok'
    except Exception as x: o=f"{type(x).__name__} {getattr(x,'getCondition',lambda:None)()} {str(x)[:160]}"
    print('==',name,o); print(*ev,sep='\n')
run('pv',"CREATE VIEW pv2 AS SELECT * FROM pv1; CREATE VIEW pv1 AS SELECT 1 + 1")
run('pvok',"CREATE VIEW pv3 AS SELECT 1 AS a; CREATE MATERIALIZED VIEW m AS SELECT * FROM pv3")
print(s.catalog.tableExists('pv2'), s.catalog.tableExists('pv1'))
s.stop()
