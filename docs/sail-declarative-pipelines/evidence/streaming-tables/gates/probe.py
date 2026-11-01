"""Spark 4.2.1 triggered streaming-table behaviour across runs, through Connect."""
import json, os, sys, shutil
from pathlib import Path
from pyspark.sql import SparkSession
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
s=SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir',(out/'wh').as_uri()).getOrCreate()
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry as Reg
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run
res=[]
def run(name, sql, storage, full=False, refresh=None, dry=False, schema='default'):
    e={'name':name,'sql':sql,'events':[]}
    g=create_dataflow_graph(s,'spark_catalog',schema,None); r=Reg(s,g)
    try:
        r.register_sql(sql,Path('p.sql'))
        for it in start_run(s,g,None,full,refresh,dry,storage):
            if 'pipeline_event_result' in it: e['events'].append(it['pipeline_event_result'].event.message)
        e['outcome']='ok'
    except Exception as x:
        e['outcome']='error'; e['type']=type(x).__name__; e['condition']=getattr(x,'getCondition',lambda:None)(); e['message']=str(x).split('\n\nJVM')[0][:700]
    res.append(e); print(name,e['outcome'],e.get('condition'),e.get('message','')[:240]); return e
def q(sql):
    try: return sorted(tuple(r) for r in s.sql(sql).collect())
    except Exception as x: return 'ERR '+str(x)[:200]
st=(out/'st1').as_uri()
s.sql("CREATE TABLE src(id INT) USING parquet"); s.sql("INSERT INTO src VALUES (1),(2)")
G="CREATE STREAMING TABLE b AS SELECT id, id*10 AS x FROM STREAM(src)"
run('first',G,st); print('b',q('select * from b'))
print('second-noop'); run('again',G,st); print('b',q('select * from b'))
s.sql("INSERT INTO src VALUES (3)"); run('incr',G,st); print('b',q('select * from b'))
run('full',G,st,full=True); print('b after full',q('select * from b'))
print(os.popen(f"cd {out}/st1 && find . -type f | grep -v crc | sed 's/[0-9a-f-]\\{{36\\}}/U/' | sort | head -40").read())
st=(out/'st2').as_uri()
G2="CREATE MATERIALIZED VIEW mv AS SELECT id FROM src; CREATE STREAMING TABLE c AS SELECT id FROM STREAM(mv)"
run('stream-of-mv',G2,st); print('c',q('select * from c'))
G3="CREATE STREAMING TABLE d AS SELECT id FROM STREAM(src); CREATE STREAMING TABLE e AS SELECT id FROM STREAM(d)"
run('chain',G3,(out/'st3').as_uri()); print('e',q('select * from e'))
G4="CREATE STREAMING TABLE f; CREATE FLOW f1 AS INSERT INTO f BY NAME SELECT id FROM STREAM(src); CREATE FLOW f2 AS INSERT INTO f BY NAME SELECT id+100 AS id FROM STREAM(src)"
run('two-flows',G4,(out/'st4').as_uri()); print('f',q('select * from f'))
G5="CREATE STREAMING TABLE g AS SELECT id FROM src"
run('batch-into-st',G5,(out/'st5').as_uri())
G6="CREATE STREAMING TABLE h AS SELECT id, count(*) c FROM STREAM(src) GROUP BY id"
run('aggregate',G6,(out/'st6').as_uri()); print('h',q('select * from h'))
G7="CREATE STREAMING TABLE i AS SELECT * FROM STREAM(RANGE(3))"
run('stream-range',G7,(out/'st7').as_uri())
G8="CREATE STREAMING TABLE j AS SELECT s.id, t.id t FROM STREAM(src) s JOIN src t ON s.id=t.id"
run('stream-static',G8,(out/'st8').as_uri()); print('j',q('select * from j'))
s.sql("INSERT OVERWRITE src VALUES (7)"); st=(out/'st1').as_uri()
run('after-overwrite',G,st); print('b',q('select * from b'))
s.stop(); (out/'obs.json').write_text(json.dumps(res,indent=1))
