"""Compare all thirteen dynamic probes without hiding unfinished computed forms."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
FINAL='ccb6fb21240b1b4d2962da833a74a17ade5e84c3'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
spark=json.loads((HERE/'spark-dynamic/observations.json').read_text());sail=json.loads((HERE/'sail-dynamic/probe/observations.json').read_text());x=json.loads((HERE/'sail-dynamic/receipt.json').read_text())
assert x['before']==x['after'] and x['before']['sail_commit']==FINAL
assert x['before']['probe_sha256']==spark['harness_sha256']==sail['harness_sha256']==digest(HERE/'reference.py')
assert x['server_exit_code']==x['probe_exit_code']==0 and x['remaining_listener_pids']==[]
for f in x['files']:assert digest(HERE/'sail-dynamic'/f['path'])==f['sha256']
assert spark['spark_version']==sail['spark_version']=='4.2.1'
assert len(spark['cases'])==len(sail['cases'])==13
def conditions(c):
 t=c.get('run_error','')+'\n'+'\n'.join(e['message'] for e in c.get('events',[]))
 return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',t)))
rows=[]
for expected,result in zip(spark['cases'],sail['cases']):
 for key in ['name','definitions','query','consumer_conf']:assert expected[key]==result[key]
 assert 'probe_error' not in result and result['session_case_sensitive']=='false'
 matched=(expected['run_returned']==result['run_returned'] and expected['result_exists']==result['result_exists'] and expected.get('rows')==result.get('rows') and conditions(expected)==conditions(result))
 rows.append({'name':result['name'],'matched':matched,'spark_conditions':conditions(expected),'sail_conditions':conditions(result),'spark_rows':expected.get('rows'),'sail_rows':result.get('rows')})
assert sum(c['matched'] for c in rows)==10,rows
assert {c['name'] for c in rows if not c['matched']}=={'computed_external_unrelated_true','cast_local','concat_local'}
print(json.dumps({'sail_commit':FINAL,'matched':10,'different':3,'scope':'thirteen public outcome/condition/row probes; computed forms unfinished, no full Scala acceptance','cases':rows},indent=2))
