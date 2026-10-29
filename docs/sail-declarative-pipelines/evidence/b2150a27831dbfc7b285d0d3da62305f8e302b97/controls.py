from pathlib import Path
import argparse,importlib.util,json,subprocess,sys
script=Path('/Users/alexy/src/sail-sdp-gate/scripts/spark-pipelines-tests/namespaces.py')
base=['--remote','sc://localhost:50084','--primary-catalog','primary','--secondary-catalog','secondary','--storage','file:///tmp/sail-sdp-namespace-matrix/control-state','--report','/tmp/sail-sdp-namespace-matrix-unused.json']
controls=[]
for name,flag,value,optimized,message in [('same_catalog','--secondary-catalog','primary',False,'two distinct catalogs'),('relative_storage','--storage','relative-path',False,'URI scheme'),('optimized',None,None,True,'Optimized Python')]:
 args=base.copy()
 if flag:args[args.index(flag)+1]=value
 cmd=[sys.executable]+(['-O'] if optimized else [])+[str(script),*args]
 result=subprocess.run(cmd,capture_output=True,text=True)
 assert result.returncode==2 and message in result.stderr,(name,result.returncode,result.stderr)
 controls.append({'name':name,'outcome':'passed','exit_code':result.returncode,'expected_message':message})
spec=importlib.util.spec_from_file_location('namespace_runner_control',script);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
original=module.check_case
def injected(*args,**kwargs):
 result=original(*args,**kwargs)
 assert result['outcome']=='passed'
 raise AssertionError('deliberate post-materialization acceptance failure')
module.check_case=injected
args=argparse.Namespace(remote='sc://localhost:50084',primary_catalog='primary',secondary_catalog='secondary',primary_provider='parquet',secondary_provider='parquet',database=None,warehouse='file:///tmp/sail-sdp-namespace-matrix/warehouse',storage='file:///tmp/sail-sdp-namespace-matrix/failure-state')
report={'cases':[]}
assert not module.execute(args,report)
assert len(report['cases'])==1 and report['cases'][0]['outcome']=='failed'
assert 'deliberate post-materialization' in report['cases'][0]['error']
assert report['cleanup']=={'outcome':'passed','errors':[]}
Path('/tmp/sail-sdp-namespace-matrix-failure-control.json').write_text(json.dumps(report,indent=2)+'\n')
controls.append({'name':'injected_post_materialization_failure','outcome':'passed','acceptance_failed':True,'cleanup':'passed'})
Path('/tmp/sail-sdp-namespace-matrix-controls.json').write_text(json.dumps(controls,indent=2)+'\n')
