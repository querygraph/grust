import json, os, sys
from pathlib import Path
from pyspark.sql import SparkSession
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
s=SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir',(out/'wh').as_uri()).getOrCreate()
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry as Reg
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run
res={}
def run(name, sql, dry=False, full=None, refresh=None):
    g=create_dataflow_graph(s,'spark_catalog','default',None); r=Reg(s,g); ev=[]
    try:
        r.register_sql(sql,Path('p.sql'))
        for it in start_run(s,g,full,False,refresh,dry,(out/('s'+name)).as_uri()):
            if 'pipeline_event_result' in it: ev.append(it['pipeline_event_result'].event.message[:230])
        o='ok'
    except Exception as x: o=f"{type(x).__name__} {getattr(x,'getCondition',lambda:None)()} {str(x)[:200]}"
    res[name]={'outcome':o,'events':ev}; print('==',name,o[:160]); print(*ev,sep='\n')
s.sql("CREATE TABLE src(id INT) USING parquet"); s.sql("INSERT INTO src VALUES (1)")
run('mv',"CREATE MATERIALIZED VIEW m1 AS SELECT id FROM src")
run('dry',"CREATE MATERIALIZED VIEW m2 AS SELECT id FROM src",dry=True)
run('chain',"CREATE MATERIALIZED VIEW m3 AS SELECT id FROM src; CREATE MATERIALIZED VIEW m4 AS SELECT id FROM m3; CREATE TEMPORARY VIEW v1 AS SELECT id FROM m4; CREATE MATERIALIZED VIEW m5 AS SELECT id FROM v1")
run('fail',"CREATE MATERIALIZED VIEW f1 AS SELECT 1/(id-1) AS d FROM src; CREATE MATERIALIZED VIEW f2 AS SELECT d FROM f1; CREATE MATERIALIZED VIEW f3 AS SELECT id FROM src")
run('select',"CREATE MATERIALIZED VIEW e1 AS SELECT id FROM src; CREATE MATERIALIZED VIEW e2 AS SELECT id FROM src",refresh=['e1'])
s.stop(); (out/'events.json').write_text(json.dumps(res,indent=1))
