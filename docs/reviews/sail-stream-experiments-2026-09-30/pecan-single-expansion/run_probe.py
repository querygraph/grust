"""Run exact Pecan client tests against a real older Sail server, storage receipts stubbed locally."""
from pathlib import Path
import importlib.util,os,subprocess,sys,datetime,json
repo=Path('/private/tmp/sail-pecan-single-expansion-gate')
out=Path('/private/tmp/pecan-single-expansion-evidence')
binary='/Users/alexy/src/sail-extensions-poc/target/extensions-datafusion-final/mac-arm64-de8e67098/artifacts/sail'
spec=importlib.util.spec_from_file_location('fixture',repo/'examples/extensions/tests/conftest.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
label=sys.argv[1]
with f.start_server(binary,out/('server-'+label)) as endpoint:
    env=dict(os.environ,SAIL_GRAPH_TEST_REMOTE=endpoint,PECAN_PROBE_STAGING=str(out/('staging-'+label)),
             PYTHONPATH=str(out)+os.pathsep+str(repo/'examples/extensions/graph-algorithms/src'),
             CARGO_INCREMENTAL='0',CARGO_TARGET_DIR='/private/tmp/sail-pecan-single-expansion-target')
    command=[sys.executable,'-m','pytest','-p','probe_receipts','-q','examples/extensions/graph-algorithms/tests/test_traversal.py',*sys.argv[2:]]
    with (out/(label+'.log')).open('w') as log:
        result=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT)
    print((out/(label+'.log')).read_text(),flush=True)
    (out/(label+'-receipt.json')).write_text(json.dumps({'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'label':label,'command':command,'returncode':result.returncode,'binary':binary,'runtime_sha':'de8e670989edb8ed5343764c52d0d002b6b6cd63','client_base_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'limitations':'Real Sail SQL and Parquet operations with test-only local GraphUtils receipt substitute. Not target-runtime, GraphUtils, distributed, or performance qualification.'},indent=2)+'\n')
    raise SystemExit(result.returncode)
