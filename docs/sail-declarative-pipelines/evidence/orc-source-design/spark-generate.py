from pathlib import Path
from datetime import datetime,timezone
import json,os,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
from pyarrow import orc
root=Path('/tmp/sail-sdp-orc-reference');root.mkdir(exist_ok=True);data=root/'data';data.mkdir(exist_ok=True)
s=SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'spark_version':s.version,'orc_compression':s.conf.get('spark.sql.orc.compression.codec'),'default_source':s.conf.get('spark.sql.sources.default'),'cases':[]}
queries={
 'range':'SELECT * FROM RANGE(3)',
 'primitive':"SELECT * FROM VALUES (CAST(1 AS BIGINT), 'a', true), (CAST(NULL AS BIGINT), CAST(NULL AS STRING), CAST(NULL AS BOOLEAN)), (CAST(3 AS BIGINT), 'é', false) AS t(id, label, flag)",
 'logical_types':"SELECT timestamp_ntz'2020-01-02 03:04:05.123456' AS ntz, timestamp'2020-01-02 03:04:05.123456' AS ltz, date'2020-01-02' AS d, CAST(12.34 AS DECIMAL(10,2)) AS amount, array(1,2) AS xs, named_struct('k', 3) AS nested",
 'empty':'SELECT * FROM RANGE(0)'}
try:
 for name,sql in queries.items():
  try:
   out=data/name
   s.sql(sql).coalesce(1).write.format('orc').mode('overwrite').save(str(out))
   frame=s.read.orc(str(out));rows=[row.asDict(recursive=True) for row in frame.collect()]
   files=sorted(out.glob('*.orc'));physical=[]
   for file in files:
    reader=orc.ORCFile(file);physical.append({'path':str(file),'compression':reader.compression,'schema':str(reader.schema),'rows':reader.read().to_pylist()})
   r['cases'].append({'name':name,'sql':sql,'outcome':'passed','spark_schema':frame.schema.jsonValue(),'rows':rows,'physical':physical})
  except Exception as e:r['cases'].append({'name':name,'outcome':'failed','error':str(e)})
finally:s.stop()
(root/'spark-generated.json').write_text(json.dumps(r,indent=2,default=str)+'\n');print(json.dumps(r,indent=2,default=str))
assert r['spark_version']=='4.2.1' and r['orc_compression']=='zstd' and len(r['cases'])==4 and all(c['outcome']=='passed' for c in r['cases']),r
