from pathlib import Path
import json,re
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'identifier-function-provenance'
VALIDATION=HERE.parent/'identifier-constant-validation'
def load(path):return json.loads(path.read_text())
def condition(case):
 if case.get('condition'):return case['condition']
 found=re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''));return found[0] if found else None
def compare(spark,sail):
 assert len(spark['cases'])==len(sail['cases'])
 rows=[]
 for a,b in zip(spark['cases'],sail['cases']):
  for key in ['name','query','args','setup']:assert a.get(key)==b.get(key)
  behavior=all(a.get(k)==b.get(k) for k in ['returned','rows']) and condition(a)==condition(b)
  metadata=behavior and all(a.get(k)==b.get(k) for k in ['condition','sql_state','parameters'])
  rows.append({'name':b['name'],'behavior_matched':behavior,'metadata_matched':metadata,'spark_condition':condition(a),'sail_condition':condition(b),'spark_rows':a.get('rows'),'sail_rows':b.get('rows')})
 return {'behavior_matched':sum(c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'cases':rows}
result={'sail_commit':load(HERE/'native/candidate.json')['commit'],'scope':'outcome/condition/rows; complete metadata counted separately; bare catalog and error-function failures retained'}
spark=load(HERE/'spark/observations.json');result['baseline14']=compare(spark,load(HERE/'baseline/probe/observations.json'));result['candidate14']=compare(spark,load(HERE/'candidate/probe/observations.json'))
for before,after in zip(result['baseline14']['cases'],result['candidate14']['cases']):
 if before['behavior_matched']:assert after['behavior_matched'],before
fixed={'scalar_divide_type','scalar_integral_type','scalar_remainder_type','typeof_integral'}
for c in result['candidate14']['cases']:
 if c['name'] in fixed:assert c['behavior_matched'],c
result['provenance20']=compare(load(PRIOR/'spark/observations.json'),load(HERE/'provenance/probe/observations.json'))
result['validation34']=compare(load(VALIDATION/'spark/observations.json'),load(HERE/'validation/probe/observations.json'))
result['replacement7']=compare(load(VALIDATION/'replacement-spark/observations.json'),load(HERE/'replacement/probe/observations.json'))
assert result['provenance20']['behavior_matched']==19 and result['validation34']['behavior_matched']==29 and result['replacement7']['behavior_matched']==6
print(json.dumps(result,indent=2))
