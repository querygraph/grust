from datetime import datetime,timezone
from pathlib import Path
import argparse,json,os
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
 os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['sail','spark']);args=parser.parse_args()
s=SparkSession.builder.remote('local[2]' if args.engine=='spark' else 'sc://localhost:50082').getOrCreate()
s.conf.set('spark.sql.ansi.enabled','true')
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'engine':args.engine,'spark_version':s.version,'sql':"SELECT CAST('not-an-int' AS INT)",'session_ansi':s.conf.get('spark.sql.ansi.enabled')}
try:
 s.sql(r['sql']).collect();r['outcome']='accepted'
except Exception as error:
 r.update(outcome='rejected',exception_type=type(error).__name__,message=str(error),condition=error.getCondition(),sql_state=error.getSqlState(),parameters=error.getMessageParameters())
finally:s.stop()
Path('/tmp/sail-sdp-catalog-cast-transport-'+args.engine+'.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
assert r['spark_version']=='4.2.1' and r['exception_type']=='NumberFormatException'
