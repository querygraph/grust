from pathlib import Path
import json,hashlib,re
p=Path(__file__).resolve().parent;r=json.loads((p/'observations.json').read_text())
assert r['engine']=='spark'and r['spark_version']=='4.2.1'and r['outcome']=='observed'
assert r['source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert r['harness_sha256']==hashlib.sha256((p/'reference.py').read_bytes()).hexdigest()
assert r['listener_probe_after_stop']=={'exit_code':1,'stdout':''}
expected={'external_before_view':'COLUMN_ALREADY_EXISTS','view_before_external':'COLUMN_ALREADY_EXISTS','declared_true_external_before_view':'COLUMN_ALREADY_EXISTS','graph_true_default':'COLUMN_ALREADY_EXISTS','external_without_view':'COLUMN_ALREADY_EXISTS','base_true_external_before_view':'AMBIGUOUS_REFERENCE','base_true_view_before_external':'AMBIGUOUS_REFERENCE'}
assert len(r['cases'])==7 and{c['name']for c in r['cases']}==set(expected)
for c in r['cases']:
 assert 'probe_error'not in c and not c['run_returned']and not c['result_exists']
 assert c['session_case_sensitive']==c['session_default']
 text=c.get('run_error','')+'\n'+'\n'.join(e['message']for e in c['events'])
 assert sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))==[expected[c['name']]]
assert r['direct_controls'][0]=={'case_sensitive':'true','rows':[{'upper_value':1,'lower_value':2}]}
assert r['direct_controls'][1]['case_sensitive']=='false'and'[COLUMN_ALREADY_EXISTS]'in r['direct_controls'][1]['error']
assert list((p/'input').glob('*.parquet'))
print('PASS seven exact Spark metadata/semantic outcomes plus two direct controls; read-order-sensitive metadata premise NOT established')
