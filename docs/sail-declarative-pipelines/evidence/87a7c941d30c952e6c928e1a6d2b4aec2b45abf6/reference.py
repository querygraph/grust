from datetime import datetime,timezone
from pathlib import Path
import hashlib,importlib.util,json,os,tempfile
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sdp-cast-activation-reference-'))
spark=SparkSession.builder.remote('local[2]').appName('ANSI cast metadata reference').getOrCreate()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
ordinary=module('cast_tests','/tmp/sail-sdp-test_cast_errors.py');pipeline=module('catalog_cast_tests','/tmp/sail-sdp-test_catalog_cast_errors.py')
fixtures=module('pipeline_fixtures','/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/conftest.py');factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[]
for target,canonical in [('TINYINT','TINYINT'),('SMALLINT','SMALLINT'),('INT','INT'),('INTEGER','INT'),('BIGINT','BIGINT'),('FLOAT','FLOAT'),('DOUBLE','DOUBLE'),('BOOLEAN','BOOLEAN')]:
 for context in ['constant','rows']:cases.append((target+':'+context,ordinary.test_invalid_ansi_cast_has_native_metadata,[spark,target,canonical,context]))
for outer in ['CAST','TRY_CAST']:cases.append(('nested:'+outer,ordinary.test_outer_cast_keeps_the_inner_ansi_failure,[spark,outer]))
for name,sql,expression in [('quote',r"SELECT CAST('a\'b' AS INT)","'a\\'b'"),('newline',r"SELECT CAST('a\nb' AS INT)","'a\nb'"),('backslash',r"SELECT CAST('a\\b' AS INT)",r"'a\\b'")]:cases.append((name,ordinary.test_ansi_cast_reports_the_actual_escaped_value,[spark,sql,expression]))
for ansi,expression,expected in [('true',"TRY_CAST('bad' AS INT)",None),('false',"CAST('bad' AS INT)",None),('true','CAST(CAST(NULL AS STRING) AS INT)',None),('true',"CAST('12' AS INT)",12)]:cases.append(('control:'+expression,ordinary.test_ansi_cast_controls_keep_null_and_valid_results,[spark,ansi,expression,expected]))
for file_ansi in ['true','false']:cases.append(('pipeline:file-ansi-'+file_ansi,pipeline.test_catalog_cast_failure_uses_session_ansi_and_native_metadata,[spark,factory(),root,file_ansi]))
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'spark_version':spark.version,'test_sources_sha256':{name:hashlib.sha256(Path('/tmp/sail-sdp-'+name).read_bytes()).hexdigest() for name in ['test_cast_errors.py','test_catalog_cast_errors.py']},'scope':'Invokes 27 unchanged public test functions/parameter instances on local Spark Connect 4.2.1','cases':[]}
try:
 for name,function,arguments in cases:
  spark.conf.set('spark.sql.ansi.enabled','true')
  try:function(*arguments);r['cases'].append({'name':name,'outcome':'passed'})
  except Exception as error:r['cases'].append({'name':name,'outcome':'failed','error':repr(error)})
finally:spark.stop()
Path('/tmp/sail-sdp-cast-activation-reference.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
assert r['spark_version']=='4.2.1' and len(r['cases'])==27 and all(c['outcome']=='passed' for c in r['cases']),r
