from pathlib import Path
import json,re
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'catalog-analysis-boundary'
def load(path):return json.loads(path.read_text())
def conditions(case):return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('error',''))) | ({case['condition']} if case.get('condition') else set()))
def wire(case):
 result=[]
 for error in case.get('connect_errors',[]):
  m=error['metadata'];result.append({'reason':error['reason'],'domain':error['domain'],'classes':json.loads(m.get('classes','[]')),'condition':m.get('errorClass'),'sql_state':m.get('sqlState'),'parameters':json.loads(m.get('messageParameters','{}'))})
 return result

def compare(spark,sail,raw=False):
 assert len(spark['cases'])==len(sail['cases']);rows=[]
 for a,b in zip(spark['cases'],sail['cases']):
  assert a['name']==b['name']
  for key in ['query','input','site']:assert a.get(key)==b.get(key)
  match=a['returned']==b['returned'] and a.get('rows')==b.get('rows') and conditions(a)==conditions(b)
  metadata=all(a.get(k)==b.get(k) for k in ['exception_type','condition','sql_state','parameters'])
  row={'name':a['name'],'behavior_matched':match,'metadata_matched':metadata,'spark_conditions':conditions(a),'sail_conditions':conditions(b)}
  if raw:row.update(wire_matched=wire(a)==wire(b),spark_wire=wire(a),sail_wire=wire(b))
  rows.append(row)
 result={'behavior_matched':sum(c['behavior_matched'] for c in rows),'metadata_matched':sum(c['metadata_matched'] for c in rows),'cases':rows}
 if raw:result['wire_matched']=sum(c['wire_matched'] for c in rows)
 return result
spark=load(HERE/'spark/observations.json')
result={'scope':'returned/rows/explicit and embedded conditions; metadata and native reason/class hierarchy separately; all differences retained','baseline16':compare(spark,load(HERE/'baseline/probe/observations.json'),True),'candidate16':compare(spark,load(HERE/'candidate/probe/observations.json'),True)}
phase_spark=load(HERE.parent/'wrapped-catalog-identifier/spark/observations.json')
result['before48']=compare(phase_spark,load(PRIOR/'phases/probe/observations.json'));result['after48']=compare(phase_spark,load(HERE/'phases/probe/observations.json'))
arithmetic_spark=load(HERE.parent/'constant-context-lowering/spark/observations.json');result['before14']=compare(arithmetic_spark,load(PRIOR/'arithmetic/probe/observations.json'));result['arithmetic14']=compare(arithmetic_spark,load(HERE/'arithmetic/probe/observations.json'))
for before,after in [('before48','after48'),('before14','arithmetic14')]:
 new={c['name']:c for c in result[after]['cases']}
 for old in result[before]['cases']:
  if old['behavior_matched']:assert new[old['name']]['behavior_matched'],old['name']
for a,b in zip(result['baseline16']['cases'],result['candidate16']['cases']):
 if a['behavior_matched']:assert b['behavior_matched'],a['name']
for expected,actual in zip(spark['cases'],result['candidate16']['cases']):
 if expected.get('condition') in ('CATALOG_NOT_FOUND','INVALID_ATTRIBUTE_NAME_SYNTAX'):assert actual['behavior_matched'] and actual['metadata_matched'],actual['name']
 if expected.get('condition')=='CATALOG_NOT_FOUND':assert actual['wire_matched'],actual['name']
print(json.dumps(result,indent=2,ensure_ascii=False))
