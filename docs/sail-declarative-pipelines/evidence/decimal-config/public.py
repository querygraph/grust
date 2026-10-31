from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,signal,subprocess,time
from pyspark.sql import SparkSession
ROOT=Path('/Users/alexy/src/sail-sdp-gate');P=Path(sys.argv[1]);P.mkdir(exist_ok=False);commit=sys.argv[2];r0=json.load(open(sys.argv[3]));CLI=ROOT/'target/debug/sail';PORT=50095;KEY='spark.sql.legacy.allowNegativeScaleOfDecimal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
head=lambda:subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{PORT}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return {int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')}
assert head()==commit==r0['sail_commit'] and r0['outcome']=='passed' and sha(CLI)==r0['cli_sha256'];assert not owners()
oracle=json.load(open('/tmp/sail-sdp-decimal-config-spark/observations.json'))
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(__file__),'sail_commit':commit,'cli_sha256':sha(CLI),'spark_oracle_sha256':sha('/tmp/sail-sdp-decimal-config-spark/observations.json'),'cases':[]};s=None;process=None
try:
 with (P/'server.log').open('x') as out:process=subprocess.Popen([str(CLI),'spark','server','--port',str(PORT)],cwd=ROOT,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
 r['server_pid']=process.pid;deadline=time.monotonic()+30
 while not owners():
  assert process.poll() is None and time.monotonic()<deadline;time.sleep(.1)
 assert owners()=={process.pid};s=SparkSession.builder.remote(f'sc://localhost:{PORT}').create();r['spark_version']=s.version;assert s.version=='4.2.1';r['default']=s.conf.get(KEY)
 for o in oracle['cases']:
  s.conf.set(KEY,'true');c={'value':o['value'],'before':s.conf.get(KEY)};r['cases'].append(c)
  try:s.conf.set(KEY,c['value']);c['accepted']=True
  except Exception as e:c.update(accepted=False,exception_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
  c['after']=s.conf.get(KEY);c['query_rows']=[list(x) for x in s.sql('SELECT 1 AS value').collect()]
 s.conf.unset(KEY);r['after_unset']=s.conf.get(KEY)
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=sorted(owners()));(P/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids'] and head()==commit and sha(CLI)==r['cli_sha256']
assert r['default']==oracle['default'] and r['after_unset']==oracle['after_unset']
for o,c in zip(oracle['cases'],r['cases']):
 assert all(c.get(k)==v for k,v in o.items()),(o,c)
 assert c['query_rows']==[[1]]
print('PASS public config12 matches Spark accepted/raw/rollback/exception/condition/state/params; queries survive each setting')
