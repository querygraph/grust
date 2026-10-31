"""Verify complete ordinary diagnostics and close the two retained metadata gaps."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
FINAL='95c32c055712995e06a56fc5c0a86d09bc3c954f'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def checked(folder,probe):
 root=HERE/folder;x=json.loads((root/'receipt.json').read_text())
 assert x['before']==x['after'] and x['before']['sail_commit']==FINAL
 assert x['before']['probe_sha256']==digest(HERE/probe)
 assert x['server_exit_code']==x['probe_exit_code']==0 and x['remaining_listener_pids']==[]
 for f in x['files']:assert digest(root/f['path'])==f['sha256']
 return json.loads((root/'probe/observations.json').read_text())
reference=json.loads((HERE/'spark/observations.json').read_text());actual=checked('sail-ordinary','reference.py')
assert reference['spark_version']==actual['spark_version']=='4.2.1'
assert reference['harness_sha256']==actual['harness_sha256']==digest(HERE/'reference.py')
assert len(reference['cases'])==len(actual['cases'])==10
ordinary=[]
for expected,result in zip(reference['cases'],actual['cases']):
 keys=['name','sql','case_sensitive','outcome']
 keys+=['rows'] if expected['outcome']=='success' else ['exception_type','condition','sql_state','parameters']
 assert {k:expected[k] for k in keys}=={k:result[k] for k in keys},(expected,result)
 ordinary.append({'name':result['name'],'matched':True,'condition':result.get('condition'),'parameters':result.get('parameters')})
old=HERE.parent/'flow-config-external-read-reference'
reference=json.loads((old/'observations.json').read_text());actual=checked('sail-external','external-reference.py')
assert digest(HERE/'external-reference.py')==digest(HERE.parent/'parquet-column-validation/external-reference.py')
for path in (old/'input').rglob('*'):
 if path.is_file():assert digest(path)==digest(HERE/'sail-external/probe/mixed-case-input'/path.relative_to(old/'input'))
def conditions(case):
 text=case.get('run_error',case.get('error',''))+'\n'+'\n'.join(e['message'] for e in case.get('events',[]))
 return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))
metadata=[]
for expected,result in zip(reference['direct_controls'],actual['direct_controls']):
 assert expected['case_sensitive']==result['case_sensitive'] and expected.get('rows')==result.get('rows')
 assert conditions(expected)==conditions(result)
 metadata.append({'name':'direct_'+result['case_sensitive'],'matched':True,'conditions':conditions(result)})
assert len(reference['cases'])==len(actual['cases'])==7
for expected,result in zip(reference['cases'],actual['cases']):
 for key in ['name','definitions','query','consumer_conf','session_default','graph_conf']:
  assert json.dumps(expected[key],sort_keys=True).replace(reference['input_uri'],'<INPUT>')==json.dumps(result[key],sort_keys=True).replace(actual['input_uri'],'<INPUT>')
 assert 'probe_error' not in result
 for key in ['run_returned','result_exists','session_case_sensitive']:assert expected[key]==result[key]
 assert expected.get('rows')==result.get('rows') and conditions(expected)==conditions(result),(expected,result)
 if result['name'].startswith('base_true'):
  text='\n'.join(e['message'] for e in expected['events'])
  first=re.search(r'Error: (\[AMBIGUOUS_REFERENCE\].*?) SQLSTATE:',text)
  assert first is not None and result['run_error']==first.group(1)
 metadata.append({'name':result['name'],'matched':True,'conditions':conditions(result)})
assert len(metadata)==9
print(json.dumps({'sail_commit':FINAL,'scope':'10 ordinary SQL outcomes with complete error metadata or rows; original-byte metadata9/9 conditions/rows and two ambiguity first-line messages; not complete origin/provenance or original Scala acceptance','ordinary_matched':10,'metadata_matched':9,'mismatched':0,'ordinary':ordinary,'metadata':metadata},indent=2,ensure_ascii=False))
