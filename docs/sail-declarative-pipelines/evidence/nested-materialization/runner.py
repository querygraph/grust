from pathlib import Path
from datetime import datetime,timezone
import os,json,subprocess,time,hashlib,signal,traceback,shutil,xml.etree.ElementTree as ET
root=Path('/Users/alexy/src/sail-sdp-gate'); out=Path('/tmp/sail-sdp-nested-public-02'); out.mkdir(exist_ok=False)
py='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'; commit='f6f13281929812482529446ce6edcc3eeac0a069'
r={'commit':commit,'started':datetime.now(timezone.utc).isoformat(),'checks':[]}; process=None
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def state():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==commit
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:50090','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
 assert p.returncode in (0,1)
 return {int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')}
def run(name,command,env):
 with (out/(name+'.log')).open('x') as log:p=subprocess.run(command,cwd=root,env={**os.environ,**env},stdout=log,stderr=subprocess.STDOUT)
 r['checks'].append({'name':name,'command':command,'exit_code':p.returncode,'sha256':sha(out/(name+'.log'))}); assert p.returncode==0,name
 state(); print('PASS '+name,flush=True)
try:
 state()
 prior=json.loads(Path('/tmp/sail-sdp-ctas-public/receipt.json').read_text());assert prior['outcome']=='passed'
 changed=subprocess.check_output(['git','diff','--name-only',prior['commit'],commit],cwd=root,text=True).splitlines()
 assert changed==['python/pysail/tests/spark/pipelines/test_nested_materialization.py']
 assert sha(root/'target/debug/sail')==prior['cli_sha256']
 r['reused_cli_from']=prior['commit'];r['changed_paths']=changed
 cli=root/'target/debug/sail'; r['cli_sha256']=sha(cli); assert not owners()
 with (out/'server.log').open('x') as log:
  process=subprocess.Popen([str(cli),'spark','server','--port','50090'],cwd=root,env={**os.environ,'PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv'},stdout=log,stderr=subprocess.STDOUT)
  r['server_pid']=process.pid
  deadline=time.monotonic()+30
  while not owners():
   assert process.poll() is None and time.monotonic()<deadline
   time.sleep(.25)
  assert owners()=={process.pid}
  nodes=['python/pysail/tests/spark/pipelines/test_nested_materialization.py']
  env={'PYTHONPATH':'python','SPARK_REMOTE':'sc://localhost:50090','PYTHONDONTWRITEBYTECODE':'1'}
  run('pytest',[py,'-m','pytest','-q',*nodes,'--junitxml='+str(out/'pytest.xml')],env)
  suite=ET.parse(out/'pytest.xml').getroot().find('testsuite'); assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('2','0','0','0')
  assert sha(cli)==r['cli_sha256'] and owners()=={process.pid}
 r['outcome']='passed'
except BaseException:
 r['outcome']='failed';r['error']=traceback.format_exc();raise
finally:
 if process:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit']=process.returncode;r['remaining_owners']=list(owners())
 r['finished']=datetime.now(timezone.utc).isoformat();(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
