from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,hashlib,signal,subprocess,time
import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import SparkSession
ROOT=Path('/Users/alexy/src/sail-sdp-gate');P=Path(sys.argv[1]);P.mkdir(exist_ok=False);PORT=50095;CLI=ROOT/'target/debug/sail';COMMIT='63f5bd3b3f0f8bd9b23607161d5988df853a738c'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
head=lambda:subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
def owners():
 p=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{PORT}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True);assert p.returncode in(0,1);return {int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')}
qualified=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-public-regression/receipt.json').read_text());assert head()==COMMIT==qualified['sail_commit'] and qualified['outcome']=='passed' and sha(CLI)==qualified['cli_sha256'];assert not owners()
oracle=json.loads(Path('/tmp/sail-sdp-source-folding-spark/observations.json').read_text());assert oracle['spark_version']=='4.2.1' and len(oracle['cases'])==56
r={'started_at':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(__file__),'sail_commit':COMMIT,'cli_sha256':sha(CLI),'spark_oracle_sha256':sha('/tmp/sail-sdp-source-folding-spark/observations.json'),'cases':[]};s=None;process=None
try:
 with (P/'server.log').open('x') as out:process=subprocess.Popen([str(CLI),'spark','server','--port',str(PORT)],cwd=ROOT,env={**os.environ,'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'},stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
 r['server_pid']=process.pid;deadline=time.monotonic()+30
 while not owners():
  assert process.poll() is None and time.monotonic()<deadline;time.sleep(.1)
 assert owners()=={process.pid};s=SparkSession.builder.remote(f'sc://localhost:{PORT}').create();r['spark_version']=s.version;assert s.version=='4.2.1'
 for name,value in [('pq_null',None),('pq_zero',0)]:
  file=P/(name+'.parquet');pq.write_table(pa.table({'d':pa.array([value],type=pa.int32())}),file);s.read.parquet(str(file)).createOrReplaceTempView(name)
 for o in oracle['cases']:
  s.conf.set('spark.sql.ansi.enabled',str(o['ansi']).lower());c={k:o[k] for k in ['ansi','target','case','query']};c['effective_ansi']=s.conf.get('spark.sql.ansi.enabled');r['cases'].append(c);phase='sql'
  try:
   frame=s.sql(c['query']);phase='explain';frame.explain();c['explain']='passed';phase='collect';rows=frame.collect();c.update(returned=True,rows=[list(x) for x in rows],schema=frame.schema.jsonValue())
  except Exception as e:c.update(returned=False,phase=phase,exception_type=type(e).__name__,condition=e.getCondition(),sql_state=e.getSqlState(),parameters=e.getMessageParameters())
finally:
 if s is not None:s.stop()
 if process is not None:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=30)
  except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
  r['server_exit_code']=process.returncode
 r.update(completed_at=datetime.now(timezone.utc).isoformat(),remaining_listener_pids=sorted(owners()));(P/'observations.json').write_text(json.dumps(r,indent=2,default=str)+'\n')
assert not r['remaining_listener_pids'] and head()==COMMIT and sha(CLI)==r['cli_sha256'];print('Sail source-folding56 recorded; no listener')
