from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,math,signal,subprocess,time
from pyspark.sql import SparkSession
ROOT=Path('/Users/alexy/src/sail-sdp-gate');P=Path(sys.argv[1]);P.mkdir(exist_ok=False)
commit=sys.argv[2];receipt=json.loads(Path(sys.argv[3]).read_text());cli=ROOT/'target/debug/sail';PORT=50095
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
head=lambda:subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{PORT}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return {int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')}
def value(v):
 if v is None:return None
 if math.isnan(v):return 'NaN'
 if math.isinf(v):return '+Infinity' if v>0 else '-Infinity'
 return v.hex()
assert head()==commit and receipt['sail_commit']==commit and receipt['outcome']=='passed' and sha(cli)==receipt['cli_sha256'];assert not owners()
oracle=json.loads(Path('/tmp/sail-sdp-floating-cast-spark/observations.json').read_text())
r={'started_at':datetime.now(timezone.utc).isoformat(),'sail_commit':commit,'cli_sha256':sha(cli),'script_sha256':sha(__file__),'spark_oracle_sha256':sha('/tmp/sail-sdp-floating-cast-spark/observations.json'),'cases':[]};s=None;process=None
try:
 with (P/'server.log').open('x') as log:process=subprocess.Popen([str(cli),'spark','server','--port',str(PORT)],cwd=ROOT,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 r['server_pid']=process.pid;deadline=time.monotonic()+30
 while not owners():
  assert process.poll() is None and time.monotonic()<deadline;time.sleep(.1)
 assert owners()=={process.pid};s=SparkSession.builder.remote(f'sc://localhost:{PORT}').create();r['spark_version']=s.version;assert s.version=='4.2.1'
 for o in oracle['cases']:
  s.conf.set('spark.sql.ansi.enabled',str(o['ansi']).lower());c={k:o[k] for k in ['ansi','target','is_try','source','query']};c['effective_ansi']=s.conf.get('spark.sql.ansi.enabled');r['cases'].append(c)
  try:
   frame=s.sql(c['query']);rows=frame.collect();c.update(returned=True,values=[value(x[0]) for x in rows],schema=frame.schema.jsonValue())
  except Exception as e:c.update(returned=False,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
  c['behavior_match']=c['returned']==o['returned'] and (c.get('values')==o.get('values') if o['returned'] else c.get('condition')==o.get('condition') and c.get('sql_state')==o.get('sql_state'))
  c['schema_match']=c.get('schema')==o.get('schema') if o['returned'] and c['returned'] else None
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=sorted(owners()));(P/'observations.json').write_text(json.dumps(r,indent=2)+'\n')
assert not r['remaining_listener_pids'] and head()==commit and sha(cli)==r['cli_sha256']
print('Recorded136 public floating casts; behavior matches',sum(c['behavior_match'] for c in r['cases']))
