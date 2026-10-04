from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,time
root=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/logging02-monitor')
latest=json.loads(sorted(root.glob('observation-*.json'))[-1].read_text())
elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(latest['local_started_utc'])).total_seconds()
time.sleep(max(0,min(60,60-elapsed)))
for _ in range(20):
 started=time.monotonic()
 run=subprocess.run(['python3',str(root/'observe.py')],text=True,capture_output=True)
 if run.returncode:
  print(json.dumps({'observer_returncode':run.returncode,'stderr':run.stderr}),flush=True);break
 p=sorted(root.glob('observation-*.json'))[-1];d=json.loads(p.read_text());o=d.get('observation',{});rows=[]
 for line in o.get('files',{}).get('memory-samples.jsonl',{}).get('tail_utf8','').splitlines():
  try:rows.append(json.loads(line))
  except ValueError:pass
 sample=rows[-1] if rows else{}
 print(json.dumps({'file':p.name,'utc':d.get('finished_utc'),'state':d.get('state',{}).get('Status'),'phase':sample.get('phase'),'rss_bytes':sample.get('rss_bytes'),'pss_bytes':sample.get('pss_bytes'),'cgroup_current':o.get('cgroup',{}).get('memory.current'),'cgroup_peak':o.get('cgroup',{}).get('memory.peak'),'events':o.get('cgroup',{}).get('memory.events'),'free_bytes':o.get('volume_free_bytes'),'errors':o.get('error_scan',{}).get('matches'),'capture_returncode':d.get('capture',{}).get('returncode'),'outer_returncode':d.get('returncode')}),flush=True)
 if d.get('inspection',{}).get('returncode') or d.get('state',{}).get('Running') is False:break
 time.sleep(max(0,60-(time.monotonic()-started)))
