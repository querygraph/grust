import argparse,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['spark','sail']);args=parser.parse_args()
reference=json.loads(Path('/tmp/sail-sdp-cast-design-spark.json').read_text())
actual=json.loads(Path('/tmp/sail-sdp-cast-design-'+args.engine+'.json').read_text())
assert actual['spark_version']==reference['spark_version']=='4.2.1'
assert len(actual['cases'])==len(reference['cases'])==24
checks=[]
for expected,observed in zip(reference['cases'],actual['cases'],strict=True):
 assert (observed['name'],observed['sql'],observed['ansi'])==(expected['name'],expected['sql'],expected['ansi'])
 fields=['outcome','rows'] if expected['outcome']=='accepted' else ['outcome','exception_type','condition','sql_state','parameters']
 mismatches={key:{'expected':expected.get(key),'actual':observed.get(key)} for key in fields if observed.get(key)!=expected.get(key)}
 checks.append({'name':observed['name'],'outcome':'failed' if mismatches else 'passed','mismatches':mismatches})
r={'engine':args.engine,'scope':'Paired public SELECT casts: class, condition, SQL state, complete message parameters or exact accepted rows; no full message/query-context assertion','passed':sum(c['outcome']=='passed' for c in checks),'failed':sum(c['outcome']=='failed' for c in checks),'checks':checks}
Path('/tmp/sail-sdp-cast-design-assertions-'+args.engine+'.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
raise SystemExit(bool(r['failed']))
