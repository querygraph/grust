from pathlib import Path
import json,sys
P=Path(__file__).resolve().parent
r=json.loads((P/'conditional-cast-comparison.json').read_text())
failed=[x for x in r['cases'] if not x['matched']]
print('Required conditional-cast conformance mismatches: '+str(len(failed)))
for x in failed:print(x['representation'],x['ansi'],x['target'],x['zero'],x['spark_condition'],x['sail_conditions'])
sys.exit(bool(failed))
