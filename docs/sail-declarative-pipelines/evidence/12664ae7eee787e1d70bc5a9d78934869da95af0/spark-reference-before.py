import importlib.util
import json
import os
import tempfile
from pathlib import Path
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sail-sdp-spark-lifecycle-'))
spark=(SparkSession.builder.remote('local[2]').appName('Sail SDP lifecycle reference')
       .config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate())
source=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
tests=module('lifecycle_tests',source/'test_execution.py')
fixtures=module('lifecycle_fixtures',source/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
results={'spark_version':spark.version,'cases':[]}
cases=[
 ('completed_dry',lambda:tests.test_graph_can_only_be_started_once(spark,factory(),True)),
 ('completed_real',lambda:tests.test_graph_can_only_be_started_once(spark,factory(),False)),
 ('failed_analysis',lambda:tests.test_failed_analysis_still_reserves_the_graph(factory())),
 ('missing_storage',lambda:tests.test_missing_storage_does_not_reserve_the_graph(spark,factory())),
]
for options,message in [
 ({'refresh':['output'],'full_refresh_all':True},'Cannot specify a subset to refresh'),
 ({'full_refresh':['output'],'full_refresh_all':True},'Cannot specify a subset to full refresh'),
 ({'refresh':['output'],'full_refresh':['default.output']},'cannot overlap')]:
    cases.append(('invalid_selection_'+str(len(cases)),lambda options=options,message=message:tests.test_invalid_refresh_selection_does_not_publish(spark,factory(),options,message)))
try:
    for name,call in cases:
        spark.sql('DROP TABLE IF EXISTS output')
        try:
            call()
            results['cases'].append({'name':name,'outcome':'passed'})
        except Exception as error:
            results['cases'].append({'name':name,'outcome':'failed','type':type(error).__name__,'message':str(error)})
finally:
    spark.stop()
Path('/tmp/sail-sdp-spark-lifecycle-reference.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
assert all(case['outcome']=='passed' for case in results['cases'])
