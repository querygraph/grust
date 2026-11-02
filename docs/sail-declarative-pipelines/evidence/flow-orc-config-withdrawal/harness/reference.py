from pathlib import Path
from datetime import datetime, timezone
import hashlib, importlib.util, json, os, subprocess, sys, traceback
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
root=Path('/tmp/sail-sdp-flow-config-reference')
root.mkdir(exist_ok=False)
probe=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
assert probe.returncode==1 and not probe.stdout
from pyspark.sql import SparkSession
source=Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/test_flow_file_config.py')
digest=hashlib.sha256(source.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('flow_config_reference_tests',source)
tests=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
spark=None
r={'started':datetime.now(timezone.utc).isoformat(),'test_source':str(source),'test_sha256':digest,'scope':'Direct executions of the three generic public test functions against Spark Connect; Sail-only capability guard excluded','cases':[]}
try:
    spark=SparkSession.builder.remote('local[2]').appName('SDP flow config reference').config('spark.ui.enabled','false').config('spark.sql.warehouse.dir',(root/'warehouse').as_uri()).getOrCreate()
    r['spark_version']=spark.version
    assert spark.version=='4.2.1'
    for name,graph,flow,read,merged in [('graph-default','true',None,None,True),('flow-overrides-graph','true','false',None,False),('read-option-overrides-flow','false','false','true',True)]:
        path=root/name;path.mkdir()
        fixture=tests.native_orc_pipeline_session.__wrapped__(spark)
        session=next(fixture)
        directory=tests.evolving_orc_files.__wrapped__(path)
        try:
            tests.test_orc_schema_merge_uses_graph_flow_and_read_precedence(session,directory,path,graph,flow,read,merged)
            r['cases'].append({'name':name,'outcome':'passed'})
        except Exception:
            r['cases'].append({'name':name,'outcome':'failed','error':traceback.format_exc()})
        finally:
            try:next(fixture)
            except StopIteration:pass
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    assert len(r['cases'])==3 and all(c['outcome']=='passed' for c in r['cases'])
    r['outcome']='passed'
except BaseException:
    r['outcome']='failed';r['error']=traceback.format_exc();raise
finally:
    if spark:spark.stop()
    r['finished']=datetime.now(timezone.utc).isoformat()
    (root/'reference.json').write_text(json.dumps(r,indent=2)+'\n')
print('PASS Spark4.2.1 direct reference cases: 3',flush=True)
