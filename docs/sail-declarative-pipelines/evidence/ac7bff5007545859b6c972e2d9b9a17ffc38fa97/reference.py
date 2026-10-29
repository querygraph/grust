import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sail-sdp-view-source-'))
spark=SparkSession.builder.remote('local[2]').appName('SDP view source reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
base=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
tests=module('view_source_tests',base/'test_view_source.py')
fixtures=module('view_source_fixtures',base/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
result={'spark_version':spark.version,'test_source_sha256':hashlib.sha256((base/'test_view_source.py').read_bytes()).hexdigest(),'cases':[]}
try:
    for context in ('ordinary','pipeline'):
        for query,rows in [('SELECT * FROM range(1, 4)',[(1,),(2,),(3,)]),("SELECT  /* inside ; */ 'é;雪' AS `值`",[('é;雪',)])]:
            case={'context':context,'query':query}
            try:
                tests.test_catalog_retains_original_view_query(spark,factory,root,context,query,rows)
                case['outcome']='passed'
            except Exception as error:
                case.update(outcome='failed',error=repr(error))
            result['cases'].append(case)
finally:
    spark.stop()
Path('/tmp/sail-sdp-view-source-integration-reference.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
assert result['spark_version']=='4.2.1' and all(c['outcome']=='passed' for c in result['cases']), result
