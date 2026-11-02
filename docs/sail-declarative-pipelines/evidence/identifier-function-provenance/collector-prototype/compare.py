from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'identifier-constant-validation'
def load(path):return json.loads(path.read_text())
def condition(case):
 if case.get('condition'):return case['condition']
 found=re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''));return found[0] if found else None
def compare(expected,actual):
 assert len(expected['cases'])==len(actual['cases'])
 rows=[]
 for a,b in zip(expected['cases'],actual['cases']):
  for key in ['name','query','args','setup']:assert a.get(key)==b.get(key)
  behavior=all(a.get(k)==b.get(k) for k in ['returned','rows']) and condition(a)==condition(b)
  metadata=behavior and all(a.get(k)==b.get(k) for k in ['condition','sql_state','parameters'])
  rows.append({'name':b['name'],'behavior_matched':behavior,'metadata_matched':metadata,'spark_condition':condition(a),'sail_condition':condition(b),'spark_returned':a['returned'],'sail_returned':b['returned'],'spark_rows':a.get('rows'),'sail_rows':b.get('rows')})
 return {'behavior_matched':sum(c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'cases':rows}
report={'scope':'public outcomes/rows and textual or structured conditions; complete condition/state/parameters counted separately; full Spark SDP goal open','sail_commit':load(HERE/'native/candidate.json')['commit']}
spark=load(HERE/'spark/observations.json')
report['baseline20']=compare(spark,load(HERE/'baseline/probe/observations.json'))
report['candidate20']=compare(spark,load(HERE/'candidate/probe/observations.json'))
report['validation34']=compare(load(PREVIOUS/'spark/observations.json'),load(HERE/'validation/probe/observations.json'))
report['replacement7']=compare(load(PREVIOUS/'replacement-spark/observations.json'),load(HERE/'replacement/probe/observations.json'))
for c in report['candidate20']['cases']:
 assert c['behavior_matched']==(c['name']!='udf_typeof'),c
for before,after in zip(report['baseline20']['cases'],report['candidate20']['cases']):
 if before['behavior_matched']:assert after['behavior_matched'],before
old=load(PREVIOUS/'comparison.json')['candidate34']['cases']
for before,after in zip(old,report['validation34']['cases']):
 assert before['name']==after['name']
 if before['behavior_matched']:assert after['behavior_matched'],before
assert next(c for c in report['validation34']['cases'] if c['name']=='scalar_dead_current_catalog')['behavior_matched']
print(json.dumps(report,indent=2))
