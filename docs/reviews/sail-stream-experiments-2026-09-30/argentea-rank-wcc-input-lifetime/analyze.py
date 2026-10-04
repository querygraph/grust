"""Summarize all matched cells from the final exact component gate."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
out=Path(__file__).parent
log=out/'extended-exact-gate/core-release.log'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
pattern=r'RANK_WCC_INPUT_LIFETIME n=\d+ degree=\d+ kind=\w+ release=(?:true|false) allocation_calls=\d+ allocated_bytes=\d+ peak_requested_bytes=\d+ retained_admitted_bytes=\d+ peak_admitted_bytes=\d+ work=\d+'
for match in re.findall(pattern,log.read_text()):
    pairs=dict(item.split('=') for item in match.split()[1:])
    rows.append({key:(value if key=='kind' else value=='true' if key=='release' else int(value)) for key,value in pairs.items()})
expected={(n,d,k,release) for n in (1,1024,65536) for d in (0,1,8) for k in ('PageRank','Residual','Reference','Star') for release in (False,True)}
indexed={(x['n'],x['degree'],x['kind'],x['release']):x for x in rows}
assert len(rows)==len(indexed)==72 and set(indexed)==expected
comparisons=[]
for n,d,kind in sorted({key[:3] for key in expected}):
    old,new=indexed[n,d,kind,False],indexed[n,d,kind,True]
    for field in ('allocation_calls','allocated_bytes','retained_admitted_bytes','work'):assert old[field]==new[field]
    assert old['peak_requested_bytes']>=new['peak_requested_bytes']
    assert old['peak_admitted_bytes']>=new['peak_admitted_bytes']
    comparisons.append(dict(n=n,degree=d,kind=kind,borrowed_peak_requested_bytes=old['peak_requested_bytes'],split_peak_requested_bytes=new['peak_requested_bytes'],requested_peak_reduction=old['peak_requested_bytes']-new['peak_requested_bytes'],borrowed_peak_admitted_bytes=old['peak_admitted_bytes'],split_peak_admitted_bytes=new['peak_admitted_bytes'],admission_peak_reduction=old['peak_admitted_bytes']-new['peak_admitted_bytes'],allocation_calls=old['allocation_calls'],allocated_bytes=old['allocated_bytes'],work=old['work']))
exact=json.loads((out/'extended-exact-gate/receipt.json').read_text());assert exact['outcome']=='PASS' and exact['exact']
result=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),commit=exact['head'],tree=exact['tree'],source_log_sha256=sha(log),rows=rows,comparisons=comparisons,summary=dict(cells=72,pairs=36,unchanged_admission_peak_pairs=sum(x['admission_peak_reduction']==0 for x in comparisons),all_allocation_volume_calls_and_work_equal=True),scope='Thread-local requested System-allocation sizes and native admission; matched borrowed vs split lifetime paths in the same exact candidate executable. Borrowed build delegates prepare/finish while retaining raw input. No RSS, elapsed-time, Linux, worker or cluster claim.')
with (out/'allocation-comparison.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result['summary']))
