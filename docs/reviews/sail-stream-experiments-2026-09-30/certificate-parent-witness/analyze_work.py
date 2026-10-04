"""Reparse every matched SQL work cell; preserve the over-cap regression."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(name):
    path=ROOT/name/'sql.xml'
    result=[]
    for prop in ET.parse(path).findall('.//property'):
        if prop.attrib['name']=='witness_work':result.append(json.loads(prop.attrib['value']))
    assert len(result)==7 and len({r['case'] for r in result})==7
    return {r['case']:r for r in result}
baseline=rows('baseline-work01');candidate=rows('exact-gate02')
assert set(baseline)==set(candidate)
pairs=[]
for case,before in baseline.items():
    after=candidate[case]
    assert before['variant']=='baseline' and after['variant']=='candidate'
    assert before['vertices']==after['vertices']
    for key,value in before['proof'].items():
        if key!='witness_rounds':assert after['proof'][key]==value,(case,key)
    counters={key:dict(before=before['counters'][key],after=after['counters'][key],
        delta=after['counters'][key]-before['counters'][key]) for key in before['counters']}
    if case.startswith('depth'):
        assert counters['graph_runs']==dict(before=1,after=0,delta=-1)
        assert counters['materializations']['after']==0
        assert counters['execute_plan_iterator_calls']['after']==18
        assert after['proof']['witness_rounds'] is None
        assert after['proof']['parent_witness_max_hops']==int(case[5:])
    elif case=='distance_only':
        assert all(row['delta']==0 for row in counters.values())
    else:
        assert counters['materializations']['delta']==counters['graph_runs']['delta']==0
        assert counters['execute_plan_iterator_calls']['delta']==1
    pairs.append(dict(case=case,vertices=before['vertices'],counters=counters,
        before_witness_rounds=before['proof']['witness_rounds'],after_witness_method=after['proof']['witness_method'],
        after_witness_rounds=after['proof']['witness_rounds'],parent_witness_max_hops=after['proof']['parent_witness_max_hops']))
receipt=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_MATCHED_WORK_CONTROL',
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'baseline-work01/sql.xml',ROOT/'exact-gate02/sql.xml',Path(__file__)]},
    raw_cells=list(baseline.values())+list(candidate.values()),pairs=pairs,
    scope='certify call only on tiny local SQL fixtures. Client ExecutePlan iterator invocations and Pecan staging calls; not elapsed time, bytes, memory, distributed jobs or graph-algorithm rounds. Input setup, schema/config RPCs and the unchanged subsequent parent validator are excluded. All seven pairs retained, including over-cap +1 call.')
with (ROOT/'work-comparison.json').open('x') as out:json.dump(receipt,out,indent=2);out.write('\n')
print(receipt['outcome'],len(pairs),'pairs',len(receipt['raw_cells']),'cells')
