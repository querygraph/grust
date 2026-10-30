from pathlib import Path
from datetime import datetime,timezone
import sys,json,subprocess,hashlib,traceback,os
sys.path.insert(0,'/tmp/sail-sdp-orc-public')
from common import candidate,snapshot,verify_build,verify_server
out=Path('/tmp/sail-sdp-orc-followup-controls.json'); assert not out.exists()
report={'started_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
try:
 expected=candidate(); build=verify_build(expected); report['before']=snapshot(expected); report['server_before']=verify_server(expected,build)
 for stem in ['orc-catalog-control-after','orc-ctas-control']:
  path=Path('/tmp/sail-sdp-'+stem+'.py'); log=Path('/tmp/sail-sdp-'+stem+'.log')
  command=[sys.executable,str(path)]
  entry={'script':str(path),'script_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'command':command}; report['checks'].append(entry)
  with log.open('x') as stream:
   r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
  entry['exit_code']=r.returncode; entry['log']=str(log); entry['log_sha256']=hashlib.sha256(log.read_bytes()).hexdigest()
  print(stem+' exit='+str(r.returncode),flush=True)
 report['after']=snapshot(expected); report['server_after']=verify_server(expected,verify_build(expected)); assert report['before']==report['after'] and report['server_before']==report['server_after']
 report['completed']=True
except BaseException:
 report['error']=traceback.format_exc(); raise
finally:
 report['completed_at']=datetime.now(timezone.utc).isoformat(); out.write_text(json.dumps(report,indent=2)+'\n')
