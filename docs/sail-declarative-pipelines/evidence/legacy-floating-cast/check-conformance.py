from pathlib import Path
import json,sys
P=Path(__file__).resolve().parent
spark=json.loads((P/'spark/observations.json').read_text())['cases']
sail=json.loads((P/'public/observations.json').read_text())['cases']
key=lambda c:(c['ansi'],c['target'],c['is_try'],c['source'])
expected={key(c):c for c in spark};assert len(expected)==len(spark)==len(sail)==136
failed=[]
for c in sail:
 o=expected[key(c)]
 match=c['returned']==o['returned'] and ((c['values']==o['values']) if o['returned'] else c['condition']==o['condition'] and c['sql_state']==o['sql_state'])
 assert c['behavior_match']==match
 expected_schema=(c.get('schema')==o.get('schema')) if c['returned'] and o['returned'] else None
 assert c['schema_match']==expected_schema
 if not match:failed.append(c)
schema_failed=[c for c in sail if c.get('schema_match') is False]
print('Required floating-cast behavior mismatches:',len(failed))
print('Required floating-cast schema mismatches:',len(schema_failed))
for c in failed:print(c['ansi'],c['target'],c['is_try'],repr(c['source']),c.get('values'),c.get('condition'))
sys.exit(bool(failed or schema_failed))
