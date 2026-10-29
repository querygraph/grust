from datetime import datetime,timezone
from pathlib import Path
import argparse,json,os,tempfile
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['spark','sail']);args=parser.parse_args()
s=SparkSession.builder.remote('local[2]' if args.engine=='spark' else 'sc://localhost:50082').getOrCreate()
root=Path(tempfile.mkdtemp(prefix='sdp-fable-response-'+args.engine+'-'))
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'engine':args.engine,'spark_version':s.version,'scope':'Targeted existing max_by execution; Spark-only AvailableNow aggregate counterexample, not Sail streaming or CDC qualification','cases':[]}
queries=[('max_by_struct',"SELECT max_by(named_struct('id', id, 'seq', seq), seq) AS winner FROM VALUES (1, 10), (2, 20) AS t(id, seq)",{'id':2,'seq':20}),('max_by_null_order',"SELECT max_by(named_struct('id', id, 'seq', seq), seq) AS winner FROM VALUES (1, CAST(NULL AS INT)), (2, 20) AS t(id, seq)",{'id':2,'seq':20}),('max_by_all_null_order',"SELECT max_by(named_struct('id', id, 'seq', seq), seq) AS winner FROM VALUES (1, CAST(NULL AS INT)), (2, CAST(NULL AS INT)) AS t(id, seq)",None)]
try:
 for name,sql,expected in queries:
  try:
   row=s.sql(sql).collect()[0];value=row.asDict(recursive=True)['winner'];assert value==expected,(value,expected)
   r['cases'].append({'name':name,'outcome':'passed','sql':sql,'winner':value})
  except Exception as error:r['cases'].append({'name':name,'outcome':'failed','sql':sql,'error':repr(error)})
 if args.engine=='spark':
  query=None
  try:
   source=root/'source';source.mkdir();checkpoint=root/'checkpoint';name='fable_state_'+root.name.replace('-','_')
   frame=s.readStream.schema('k STRING, v INT').json(str(source)).groupBy('k').sum('v')
   observations=[]
   for index,value in enumerate([1,2]):
    (source/f'{index}.json').write_text(json.dumps({'k':'x','v':value})+'\n')
    query=frame.writeStream.format('memory').queryName(name).outputMode('complete').option('checkpointLocation',str(checkpoint)).trigger(availableNow=True).start()
    assert query.awaitTermination(60), 'AvailableNow aggregate did not terminate'
    observations.append([row.asDict() for row in s.table(name).collect()])
   assert observations==[[{'k':'x','sum(v)':1}],[{'k':'x','sum(v)':3}]],observations
   isolated=s.read.schema('k STRING, v INT').json(str(source/'1.json')).groupBy('k').sum('v').collect()[0].asDict()
   assert isolated=={'k':'x','sum(v)':2},isolated
   r['cases'].append({'name':'available_now_preserves_state_across_runs','outcome':'passed','streaming_results':observations,'isolated_second_range_result':isolated,'checkpoint_reused':True,'output_mode':'complete','root':str(root)})
   s.catalog.dropTempView(name)
  except Exception as error:r['cases'].append({'name':'available_now_preserves_state_across_runs','outcome':'failed','error':repr(error),'root':str(root)})
  finally:
   if query is not None and query.isActive:query.stop()
finally:s.stop()
Path('/tmp/sail-sdp-fable-response-'+args.engine+'.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
assert r['spark_version']=='4.2.1' and all(c['outcome']=='passed' for c in r['cases']),r
