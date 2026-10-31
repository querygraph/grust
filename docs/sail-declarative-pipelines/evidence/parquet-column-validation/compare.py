"""Retain exact input identity and all metadata/partition runtime differences."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
REFERENCE=HERE.parent/'flow-config-external-read-reference'
COMMIT='005fcb07826321693c937a23f362f2e0212aa441'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def checked_run(folder,probe):
 root=HERE/folder;x=json.loads((root/'receipt.json').read_text())
 assert x['before']==x['after'] and x['before']['sail_commit']==COMMIT
 assert x['before']['probe_sha256']==digest(HERE/probe)
 assert x['server_exit_code']==x['probe_exit_code']==0 and x['remaining_listener_pids']==[]
 for f in x['files']:assert digest(root/f['path'])==f['sha256']
 return json.loads((root/'probe/observations.json').read_text())
def conditions(case):
 text=case.get('run_error',case.get('error',''))+'\n'+'\n'.join(e['message'] for e in case.get('events',[]))
 return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))
spark=json.loads((REFERENCE/'observations.json').read_text());sail=checked_run('sail-external','external-reference.py')
assert spark['spark_version']==sail['spark_version']=='4.2.1'
assert digest(HERE/'external-reference-original.py')==digest(REFERENCE/'reference.py')==spark['harness_sha256']
assert sail['harness_sha256']==digest(HERE/'external-reference.py')
for path in (REFERENCE/'input').rglob('*'):
 if path.is_file():assert digest(path)==digest(HERE/'sail-external/probe/mixed-case-input'/path.relative_to(REFERENCE/'input'))
assert len(spark['direct_controls'])==len(sail['direct_controls'])==2
rows=[]
for expected,actual in zip(spark['direct_controls'],sail['direct_controls']):
 assert expected['case_sensitive']==actual['case_sensitive']
 assert expected.get('rows')==actual.get('rows')
 assert conditions(expected)==conditions(actual)
 rows.append({'name':'direct_'+actual['case_sensitive'],'matched':True,'spark_conditions':conditions(expected),'sail_conditions':conditions(actual)})
assert len(spark['cases'])==len(sail['cases'])==7
for expected,actual in zip(spark['cases'],sail['cases']):
 assert 'probe_error' not in actual
 for key in ['name','definitions','query','consumer_conf','session_default','graph_conf']:
  left=json.dumps(expected[key],sort_keys=True).replace(spark['input_uri'],'<INPUT>')
  right=json.dumps(actual[key],sort_keys=True).replace(sail['input_uri'],'<INPUT>')
  assert left==right,(key,expected['name'])
 assert expected['session_case_sensitive']==actual['session_case_sensitive']
 assert expected['run_returned']==actual['run_returned'] and expected['result_exists']==actual['result_exists']
 assert expected.get('rows')==actual.get('rows')
 matched=conditions(expected)==conditions(actual)
 if actual['name'].startswith('base_true'):assert 'ambiguous attribute:' in actual.get('run_error','')
 rows.append({'name':actual['name'],'matched':matched,'spark_conditions':conditions(expected),'sail_conditions':conditions(actual)})
assert sum(row['matched'] for row in rows)==7
assert {r['name'] for r in rows if not r['matched']}=={'base_true_external_before_view','base_true_view_before_external'}
assert all(r['spark_conditions']==['AMBIGUOUS_REFERENCE'] and r['sail_conditions']==[] for r in rows if not r['matched'])
reference=json.loads((HERE/'spark-partition/observations.json').read_text());actual=checked_run('sail-partition','partition-reference.py')
assert reference['harness_sha256']==actual['harness_sha256']==digest(HERE/'partition-reference.py')
assert len(reference['cases'])==len(actual['cases'])==6
partitions=[]
for expected,result in zip(reference['cases'],actual['cases']):
 keys=['file_columns','case_sensitive','outcome']
 if expected['outcome']=='success':keys+=['schema','rows']
 else:keys+=['condition','sql_state','parameters']
 assert {k:expected[k] for k in keys}=={k:result[k] for k in keys},(expected,result)
 partitions.append({'file_columns':result['file_columns'],'case_sensitive':result['case_sensitive'],'matched':True})
print(json.dumps({'sail_commit':COMMIT,'scope':'same Spark-produced mixed-case input bytes: seven condition/row matches of nine, two structured ambiguity differences; six actual Parquet shadow schemas/rows or complete error metadata match; not full SDP acceptance','external_matched':7,'external_different':2,'partition_matched':6,'partition_different':0,'external':rows,'partitions':partitions},indent=2))
