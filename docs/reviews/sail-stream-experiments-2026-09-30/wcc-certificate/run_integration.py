#!/usr/bin/env python3
"""Run only tiny WCC SQL checks against the existing installed local Sail binary."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, signal, socket, subprocess, time
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
binary=Path('/Users/alexy/src/sail/.venvs/default/bin/sail');native=Path('/Users/alexy/src/sail/python/pysail/_native.abi3.so');python=Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python')
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env=dict(os.environ,SAIL_MODE='local',SAIL_EXECUTION__DEFAULT_PARALLELISM='2',TOKIO_WORKER_THREADS='2',RAYON_NUM_THREADS='2',RUST_LOG='warn',PYTHONDONTWRITEBYTECODE='1')
for key in ('PYTHONHOME','PYTHONPATH'):env.pop(key,None)
cmd=[str(python),'-m','pytest','-q','-p','no:cacheprovider',str(a.repo/'examples/extensions/benchmarks/test_wcc_certificate.py'),'--junitxml='+str(a.output/'junit.xml'),'--basetemp='+str(a.output/'pytest-temp')]
receipt=dict(recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=str(a.repo),source_head=subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip(),binary=str(binary),binary_sha256=hashfile(binary),installed_native=str(native),installed_native_sha256=hashfile(native),installed_version=subprocess.check_output([str(binary),'--version'],text=True).strip(),runtime_source_provenance='Installed executable identity only; not claimed built from the candidate source',command=cmd)
with (a.output/'server.log').open('w') as log:
 process=subprocess.Popen([str(binary),'spark','server','--ip','127.0.0.1','--port',str(port)],env=env,cwd=a.output,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  deadline=time.monotonic()+30
  while True:
   if process.poll() is not None:raise RuntimeError('server exited; inspect server.log')
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:
    if time.monotonic()>deadline:raise TimeoutError('startup timeout')
    time.sleep(.05)
  with (a.output/'tests.log').open('w') as testlog:
   result=subprocess.run(cmd,cwd=a.repo,env=dict(env,SAIL_GRAPH_TEST_REMOTE='sc://127.0.0.1:'+str(port)),stdout=testlog,stderr=subprocess.STDOUT,timeout=120)
  receipt['returncode']=result.returncode
 finally:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  receipt['server_reaped']=process.poll() is not None
  receipt['native_bytes_unchanged']=hashfile(native)==receipt['installed_native_sha256']
  receipt['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt));raise SystemExit(receipt['returncode'])
