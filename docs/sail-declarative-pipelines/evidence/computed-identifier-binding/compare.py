"""Compare all dynamic/namespace probes; retain expression diagnostic differences."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
FINAL=json.loads((HERE/'sdp/candidate.json').read_text())['commit']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def conditions(c):
 text=c.get('run_error','')+'\n'+'\n'.join(e['message'] for e in c.get('events',[]) if isinstance(e,dict))
 return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))
report={'sail_commit':FINAL,'scope':'public outcome, condition and row probes; not full metadata or Scala acceptance'}
for kind,probe,count in [('dynamic','reference.py',13),('namespace','namespace-reference.py',3),('expression','expression-reference.py',2)]:
 spark=json.loads((HERE/('spark-'+kind)/'observations.json').read_text());sail=json.loads((HERE/('sail-'+kind)/'probe/observations.json').read_text());receipt=json.loads((HERE/('sail-'+kind)/'receipt.json').read_text())
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==FINAL
 assert receipt['before']['cli_sha256']==json.loads((HERE/'public/receipt.json').read_text())['cli_sha256']
 assert receipt['before']['probe_sha256']==spark['harness_sha256']==sail['harness_sha256']==digest(HERE/probe)
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for file in receipt['files']:assert digest(HERE/('sail-'+kind)/file['path'])==file['sha256']
 assert spark['spark_version']==sail['spark_version']=='4.2.1' and len(spark['cases'])==len(sail['cases'])==count
 rows=[]
 for expected,result in zip(spark['cases'],sail['cases']):
  for key in (['name','query'] if kind=='namespace' else ['name','definitions','query','consumer_conf']):assert expected[key]==result[key]
  assert 'probe_error' not in result
  if kind=='namespace':
   matched=all(expected.get(k)==result.get(k) for k in ['returned','rows','session_namespace'])
  else:
   assert result['session_case_sensitive']=='false'
   matched=all(expected.get(k)==result.get(k) for k in ['run_returned','result_exists','rows']) and conditions(expected)==conditions(result)
  rows.append({'name':result['name'],'matched':matched,'spark_conditions':conditions(expected),'sail_conditions':conditions(result),'spark_rows':expected.get('rows'),'sail_rows':result.get('rows')})
 report[kind]={'matched':sum(c['matched'] for c in rows),'different':sum(not c['matched'] for c in rows),'cases':rows}
 if kind in ('dynamic','namespace'):assert report[kind]['matched']==count,rows
print(json.dumps(report,indent=2))
