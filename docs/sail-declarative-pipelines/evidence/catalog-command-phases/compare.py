from pathlib import Path
import json,re
HERE=Path(__file__).resolve().parent
def load(path):return json.loads((HERE/path).read_text())
def conditions(case):return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''))))
spark=load('spark/observations.json');sail=load('sail/probe/observations.json');rows=[]
assert len(spark['cases'])==len(sail['cases'])==32
for a,b in zip(spark['cases'],sail['cases']):
 assert (a['name'],a['query'],a['site'],a['wrapped'])==(b['name'],b['query'],b['site'],b['wrapped'])
 match=a['returned']==b['returned'] and a.get('rows')==b.get('rows') and conditions(a)==conditions(b)
 metadata=all(a.get(k)==b.get(k) for k in ['exception_type','condition','sql_state','parameters'])
 rows.append({'name':a['name'],'behavior_matched':match,'metadata_matched':metadata,'spark_returned':a['returned'],'sail_returned':b['returned'],'spark_conditions':conditions(a),'sail_conditions':conditions(b)})
print(json.dumps({'scope':'identical queries; returned/rows/embedded conditions; error metadata counted separately without normalization','behavior_matched':sum(c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'cases':rows},indent=2))
