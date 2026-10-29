import importlib.util,json,os,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sdp-cte-ref-'))
s=SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
def mod(name,file):
 spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines')
tests=mod('ctetests',base/'test_cte_stream.py');fixtures=mod('ctefix',base/'conftest.py')
r={'spark_version':s.version,'cases':[]}
try:
 for index,(query,expected) in enumerate(tests.test_stream_of_batch_cte.pytestmark[0].args[1]):
  try:
   pipeline=fixtures.pipeline_factory.__wrapped__(s,root/str(index))()
   tests.test_stream_of_batch_cte(s,pipeline,root/str(index),query,expected)
   r['cases'].append({'query':query,'outcome':'passed','expected':expected})
  except Exception as e:r['cases'].append({'query':query,'outcome':'failed','error':str(e)})
finally:s.stop()
Path('/tmp/sail-sdp-cte-stream-reference.json').write_text(json.dumps(r,indent=2)+'\n')
assert len(r['cases'])==4 and all(c['outcome']=='passed' for c in r['cases']),r
