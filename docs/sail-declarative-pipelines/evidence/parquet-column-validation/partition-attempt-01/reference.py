"""Observe actual Parquet file/partition shadowing through public Spark SQL."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,sys
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import SparkSession
import pyspark
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);ENGINE=sys.argv[2]
assert ENGINE in ('spark','sail')
report={'engine':ENGINE,'started_at':datetime.now(timezone.utc).isoformat(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'actual Parquet partition-shadow schemas and rows; no Scala acceptance','cases':[]}
spark=None
try:
 spark=SparkSession.builder.remote('local[1]' if ENGINE=='spark' else 'sc://localhost:50094').appName('partition shadow reference').config('spark.ui.enabled','false').getOrCreate()
 report['spark_version']=spark.version;assert spark.version==pyspark.__version__=='4.2.1'
 for columns in [('p',),('P',),('P','p')]:
  folder=OUT/('input-'+''.join(columns));file=folder/'p=directory-value'/'part.parquet';file.parent.mkdir(parents=True)
  pq.write_table(pa.table({name:['file-value-'+str(i)] for i,name in enumerate(columns)}),file)
  for sensitive in [False,True]:
   spark.conf.set('spark.sql.caseSensitive',str(sensitive).lower())
   case={'file_columns':list(columns),'case_sensitive':sensitive}
   try:
    frame=spark.read.parquet(folder.as_uri());case.update(outcome='success',schema=frame.schema.jsonValue(),rows=[r.asDict() for r in frame.collect()])
   except Exception as error:case.update(outcome='error',condition=error.getCondition(),sql_state=error.getSqlState(),parameters=error.getMessageParameters(),message=str(error))
   report['cases'].append(case)
finally:
 if spark is not None:spark.stop()
 report['completed_at']=datetime.now(timezone.utc).isoformat()
 (OUT/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded',ENGINE,'partition cases',len(report['cases']),flush=True)
