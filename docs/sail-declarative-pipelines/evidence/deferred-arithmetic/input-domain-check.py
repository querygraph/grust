"""Fail until floating DIV is rejected with Spark's analysis error in both ANSI modes."""
from pathlib import Path
import json,sys
HERE=Path(__file__).resolve().parent
spark=json.loads((HERE/'domain-spark/observations.json').read_text())['cases']
sail=json.loads((HERE/'domain-sail/probe/observations.json').read_text())['cases']
failures=[]
for expected,actual in zip(spark,sail):
 assert expected['name']==actual['name'] and expected['query']==actual['query']
 assert expected['condition']=='DATATYPE_MISMATCH.BINARY_OP_DIFF_TYPES'
 if actual.get('condition')!=expected['condition'] or actual['returned']!=expected['returned']:failures.append(actual['name'])
print(json.dumps({'scope':'required Spark floating DIV input-domain rejection','passed':len(spark)-len(failures),'failed':len(failures),'failures':failures},indent=2))
raise SystemExit(bool(failures))
