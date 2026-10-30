from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, tempfile, traceback, uuid
import pyarrow as pa
from pyarrow import orc, parquet
from pyspark.sql import SparkSession
out=Path('/tmp/sail-sdp-orc-catalog-control.json')
assert not out.exists()
server=json.loads(Path('/tmp/sail-sdp-orc-public/server.json').read_text())
result={'started_at':datetime.now(timezone.utc).isoformat(),'server':server,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[]}
spark=SparkSession.builder.remote('sc://localhost:50088').getOrCreate()
result['spark_version']=spark.version
try:
 with tempfile.TemporaryDirectory(prefix='sdp-orc-catalog-control-') as temporary:
  root=Path(temporary)
  for fmt in ('orc','parquet','json'):
   directory=root/fmt; directory.mkdir(); file=directory/('part.'+fmt)
   table=pa.table({'id':pa.array([3,1], type=pa.int32())})
   if fmt=='orc': orc.write_table(table,file)
   elif fmt=='parquet': parquet.write_table(table,file)
   else: file.write_text('{"id":3}\n{"id":1}\n')
   for explicit in (False,True):
    name='orc_control_'+uuid.uuid4().hex
    query=f"CREATE TABLE {name} {'(id INT)' if explicit else ''} USING {fmt} LOCATION '{directory}'"
    case={'format':fmt,'explicit_schema':explicit,'query':query}; result['cases'].append(case)
    before=hashlib.sha256(file.read_bytes()).hexdigest()
    try:
     direct=spark.read.format(fmt).load(str(directory))
     case['direct_schema']=direct.schema.jsonValue()
     case['direct_rows']=[list(row) for row in direct.collect()]
     spark.sql(query)
     frame=spark.table(name)
     case['table_schema']=frame.schema.jsonValue()
     case['table_rows']=[list(row) for row in frame.collect()]
     case['describe']=[list(row) for row in spark.sql('DESCRIBE TABLE '+name).collect()]
    except Exception:
     case['error']=traceback.format_exc()
    finally:
     spark.sql('DROP TABLE IF EXISTS '+name)
     case['file_unchanged']=before==hashlib.sha256(file.read_bytes()).hexdigest()
finally:
 spark.stop()
 result['completed_at']=datetime.now(timezone.utc).isoformat()
 out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['cases'],indent=2))
