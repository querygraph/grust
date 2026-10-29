import importlib.util,json,os,tempfile,subprocess
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sail-sdp-spark-publication-'))
spark=(SparkSession.builder.remote('local[2]').appName('Sail SDP publication reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate())
source=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/pipelines')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
tests=module('schema_tests',source/'test_schema.py')
fixtures=module('schema_fixtures',source/'conftest.py')
factory=fixtures.pipeline_factory.__wrapped__(spark,root)
cases=[]
for i,values in enumerate(tests.test_declared_schema_publication.pytestmark[0].args[1]):
    cases.append(('declared_type_'+str(i),lambda values=values:tests.test_declared_schema_publication(spark,factory(),*values)))
for i,values in enumerate(tests.test_missing_declared_columns_fail_after_table_materialization.pytestmark[0].args[1]):
    cases.append(('missing_column_'+str(i),lambda values=values:tests.test_missing_declared_columns_fail_after_table_materialization(spark,factory(),*values)))
cases += [
 ('order_comments',lambda:tests.test_declared_schema_publication_preserves_order_and_comments(spark,factory())),
 ('inferred_nullable',lambda:tests.test_inferred_publication_schema_is_nullable_recursively(spark,factory())),
 ('refresh_comments',lambda:tests.test_schema_refresh_updates_comments_without_reordering_existing_columns(spark,factory)),
]
cases=[cases[-1]]
results={'spark_version':spark.version,'test_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','rev-parse','HEAD'],text=True).strip(),'cases':[]}
try:
    for name,call in cases:
        spark.sql('DROP TABLE IF EXISTS output')
        try:
            call();results['cases'].append({'name':name,'outcome':'passed'})
        except Exception as error:
            results['cases'].append({'name':name,'outcome':'failed','type':type(error).__name__,'message':str(error),'schema':spark.table('output').schema.jsonValue(),'rows':[row.asDict(recursive=True) for row in spark.table('output').collect()]})
finally:
    spark.stop()
Path('/tmp/sail-sdp-spark-refresh-comments.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
assert all(case['outcome']=='passed' for case in results['cases'])
