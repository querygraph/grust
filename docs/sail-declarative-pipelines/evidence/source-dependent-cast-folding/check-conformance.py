from pathlib import Path
import json,sys
P=Path(__file__).resolve().parent
failed=0
for family in ['source-folding','decimal-contract']:
 expected=json.loads((P/family/'spark/observations.json').read_text())['cases'];actual=json.loads((P/family/'public/observations.json').read_text())['cases'];assert len(expected)==len(actual)
 passed=0
 for s,a in zip(expected,actual):
  assert s['query']==a['query'] and s['ansi']==a['ansi'] and s['target']==a['target']
  both=s['returned'] and a['returned']
  outcome=s['returned']==a['returned'] and ((s['rows']==a['rows'] if family=='source-folding' else s['values']==a['values']) if both else s.get('condition')==a.get('condition') and s.get('sql_state')==a.get('sql_state'))
  schema=s['schema']==a['schema'] if both else True
  phase=True if family=='decimal-contract' or both else (not s['returned'] and not a['returned'] and (s['phase']=='collect')==(a['phase']=='collect'))
  matched=outcome and schema and phase;passed+=matched
  if not matched:
   failed+=1;print('FAIL',family,s['ansi'],s['target'],s.get('case',repr(s.get('source'))),'outcome',outcome,'schema',schema,'phase',phase)
 print('SUMMARY',family,'matched',passed,'of',len(expected))
print('Required combined conformance failures:',failed)
sys.exit(bool(failed))
