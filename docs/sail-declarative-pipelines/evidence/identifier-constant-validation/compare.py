"""Keep behavioral validation and complete structured metadata verdicts separate."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def condition(case):
 if case.get('condition'):return case['condition']
 matches=re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''))
 return matches[0] if matches else None
def compare(spark,sail):
 assert len(spark['cases'])==len(sail['cases'])
 rows=[]
 for expected,actual in zip(spark['cases'],sail['cases']):
  for key in ['name','query','args']:assert expected[key]==actual[key]
  behavior=all(expected.get(k)==actual.get(k) for k in ['returned','rows']) and condition(expected)==condition(actual)
  metadata=behavior and all(expected.get(k)==actual.get(k) for k in ['condition','sql_state','parameters'])
  rows.append({'name':actual['name'],'behavior_matched':behavior,'metadata_matched':metadata,'spark_condition':condition(expected),'sail_condition':condition(actual),'spark_returned':expected['returned'],'sail_returned':actual['returned'],'spark_rows':expected.get('rows'),'sail_rows':actual.get('rows')})
 return {'behavior_matched':sum(c['behavior_matched'] for c in rows),'behavior_different':sum(not c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'metadata_different':sum(not c['metadata_matched'] for c in rows),'cases':rows}
result={'scope':'public outcomes/rows and textual or structured conditions; full metadata counted separately, full Spark SDP goal remains open'}
result['baseline30']=compare(load('spark30/observations.json'),load('baseline/probe/observations.json'))
result['candidate34']=compare(load('spark/observations.json'),load('candidate/probe/observations.json'))
result['replacement_initial7']=compare(load('replacement-spark/observations.json'),load('attempt-02/replacement/probe/observations.json'))
result['replacement7']=compare(load('replacement-spark/observations.json'),load('replacement/probe/observations.json'))
# Existing compatible cases may not regress; all valid parameter witnesses survive.
after={c['name']:c for c in result['candidate34']['cases']}
for before in result['baseline30']['cases']:
 if before['behavior_matched']:assert after[before['name']]['behavior_matched'],before
for name in ['table_named','table_named_concat','table_positional','scalar_named','scalar_positional','table_dead_random','table_subquery_missing_column','table_subquery_missing_table']:
 assert after[name]['behavior_matched'],after[name]
assert not after['scalar_dead_current_catalog']['behavior_matched']
assert all(c['behavior_matched'] for c in result['replacement7']['cases'] if c['name']!='catalog_typeof_random')
for folder,probe,count in [('baseline','reference30.py',30),('candidate','reference.py',34),('replacement','runtime-replacement-reference.py',7)]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(HERE/probe) and len(observed['cases'])==count
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
result['sail_commit']=load('native/candidate.json')['commit']
assert load('candidate/receipt.json')['before']['sail_commit']==load('replacement/receipt.json')['before']['sail_commit']==result['sail_commit']
print(json.dumps(result,indent=2))
