from pathlib import Path
import json,re
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'catalog-command-phases'
def load(path):return json.loads(path.read_text())
def conditions(case):return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''))))
def compare(spark,sail):
 expected={c['name']:c for c in spark['cases']};rows=[]
 for b in sail['cases']:
  a=expected[b['name']];assert a['query']==b['query']
  match=a['returned']==b['returned'] and a.get('rows')==b.get('rows') and conditions(a)==conditions(b)
  metadata=all(a.get(k)==b.get(k) for k in ['exception_type','condition','sql_state','parameters'])
  rows.append({'name':b['name'],'behavior_matched':match,'metadata_matched':metadata,'spark_returned':a['returned'],'sail_returned':b['returned'],'spark_conditions':conditions(a),'sail_conditions':conditions(b)})
 return {'behavior_matched':sum(c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'cases':rows}
spark=load(HERE/'spark/observations.json');candidate=load(HERE/'phases/probe/observations.json')
result={'scope':'outcome/rows/embedded conditions; complete metadata compared without normalization; all failures retained','original32':load(PRIOR/'comparison.json'),'reviewed48':compare(spark,load(HERE/'attempt-02/catalog48/probe/observations.json')),'candidate48':compare(spark,candidate)}
names={c['name'] for c in result['original32']['cases']}
result['candidate32']=compare(spark,{'cases':[c for c in candidate['cases'] if c['name'] in names]})
new={c['name']:c for c in result['candidate48']['cases']}
for old in result['original32']['cases']:
 if old['behavior_matched']:assert new[old['name']]['behavior_matched'],old['name']
for name in ['missing','missing_after_current','typeof_missing','typed_null']:
 assert new[f'public_wrapped_{name}']['behavior_matched']
for name in ['typeof_current','typeof_rand']:assert new['directive_wrapped_'+name]['behavior_matched']
print(json.dumps(result,indent=2))
