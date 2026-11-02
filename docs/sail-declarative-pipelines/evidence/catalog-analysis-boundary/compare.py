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
PRIOR=HERE.parent/'wrapped-catalog-identifier'
spark=load(PRIOR/'spark/observations.json');candidate=load(HERE/'phases/probe/observations.json')
before=load(PRIOR/'comparison.json')['candidate48'];after=compare(spark,candidate)
new={c['name']:c for c in after['cases']}
for old in before['cases']:
 if old['behavior_matched']:assert new[old['name']]['behavior_matched'],old['name']
for name in ['directive_wrapped_missing','directive_wrapped_missing_after_current','directive_wrapped_typeof_missing']:assert new[name]['behavior_matched'],name
print(json.dumps({'scope':'same48 queries; returned/rows/embedded conditions, metadata separate; full original Scala acceptance remains open','before48':before,'after48':after},indent=2))
