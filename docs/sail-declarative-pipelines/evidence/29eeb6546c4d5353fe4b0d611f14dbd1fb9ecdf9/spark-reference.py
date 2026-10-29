import importlib.util,json,os,subprocess,tempfile
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
root=Path(tempfile.mkdtemp(prefix='sail-sdp-spark-write-schema-'))
spark=(SparkSession.builder.remote('local[2]').appName('Sail write schema reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate())
source=Path('/Users/alexy/src/sail-sdp-gate/python/pysail/tests/spark/dataframe')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
writes=module('write_schema_tests',source/'test_write_schema.py')
comments=module('table_schema_tests',source/'test_table_schema.py')
cases=[]
for i,values in enumerate(writes.test_append_rejects_unmatched_columns.pytestmark[0].args[1]):
    cases.append(('unmatched_'+str(i),lambda location,values=values:writes.test_append_rejects_unmatched_columns(spark,location,*values)))
cases.append(('reorder_and_null',lambda location:writes.test_append_matches_nested_fields_by_name_and_accepts_explicit_null(spark,location)))
for i,comment in enumerate(comments.test_dataframe_schema_preserves_catalog_column_comments.pytestmark[0].args[1]):
    cases.append(('comment_'+str(i),lambda location,comment=comment:comments.test_dataframe_schema_preserves_catalog_column_comments(spark,location,comment)))
results={'spark_version':spark.version,'test_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','rev-parse','HEAD'],text=True).strip(),'cases':[]}
try:
    for name,call in cases:
        location=root/name;location.mkdir()
        try:
            call(location);results['cases'].append({'name':name,'outcome':'passed'})
        except Exception as error:
            results['cases'].append({'name':name,'outcome':'failed','type':type(error).__name__,'message':str(error)})
finally:
    spark.stop()
Path('/tmp/sail-sdp-spark-write-schema-reference.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
assert all(case['outcome']=='passed' for case in results['cases'])
