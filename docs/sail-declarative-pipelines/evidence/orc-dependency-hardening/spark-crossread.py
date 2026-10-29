from pathlib import Path
from datetime import datetime,timezone
import json,os
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyarrow import orc
s=SparkSession.builder.remote('local[2]').getOrCreate();r={'recorded_at':datetime.now(timezone.utc).isoformat(),'spark_version':s.version,'cases':[]}
expected={'range':[{'id':0},{'id':1},{'id':2}],'empty':[],'nullable':[{'id':0,'label':'a','flag':True},{'id':None,'label':None,'flag':None},{'id':2,'label':'','flag':False},{'id':-3,'label':'λ','flag':True},{'id':4,'label':'five','flag':False}]}
try:
 for name,want in expected.items():
  path=Path('/tmp/orc-sdp-metadata-replay/output')/(name+'.orc')
  try:
   frame=s.read.orc(str(path));rows=[row.asDict() for row in frame.collect()]
   assert rows==want,(rows,want)
   f=orc.ORCFile(path);assert f.compression=='ZSTD',f.compression
   r['cases'].append({'name':name,'outcome':'passed','rows':rows,'schema':frame.schema.jsonValue(),'compression':f.compression,'stripes':f.nstripes})
  except Exception as e:r['cases'].append({'name':name,'outcome':'failed','error':str(e)})
finally:s.stop()
Path('/tmp/orc-sdp-metadata-spark-crossread.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
assert r['spark_version']=='4.2.1' and len(r['cases'])==3 and all(c['outcome']=='passed' for c in r['cases']),r
