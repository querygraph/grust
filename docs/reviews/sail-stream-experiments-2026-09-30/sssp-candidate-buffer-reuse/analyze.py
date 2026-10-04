"""Pair every frozen baseline/candidate finish-allocation observation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cells(path):
    result = {}
    for row in re.findall(r'SSSP_REUSE algorithm=([^\n]+)', path.read_text()):
        fields = dict(re.findall(r'(\w+)=([^ ]+)', 'algorithm=' + row))
        for key in fields.keys() - {'algorithm', 'mode'}:
            fields[key] = int(fields[key])
        key = (fields['algorithm'], fields['local_vertices'], fields['mode'])
        assert key not in result
        result[key] = fields
    assert len(result) == 18
    assert set(result) == {(a, n, m) for a in ('Reference', 'DeltaStar')
                           for n in (1, 1024, 65536) for m in ('topology', 'active', 'done')}
    return result


baseline = ROOT / 'baseline03/tests.log'
candidate = ROOT / 'candidate03/tests.log'
before, after = cells(baseline), cells(candidate)
pairs = []
for key in sorted(before):
    b, a = before[key], after[key]
    assert b['partitions'] == a['partitions'] == 3
    assert b['admitted_before'] == a['admitted_before'] == 64 * 1024**2
    assert b['work'] == a['work'] and b['admitted_after'] == a['admitted_after']
    n, mode = key[1:]
    assert b['candidate_capacity'] == a['candidate_capacity'] == (0 if mode == 'done' else n)
    assert a['transferred'] == 1
    metrics = ['calls', 'bytes', 'requested_peak', 'finish_peak_admitted_delta',
               'matched_allocations', 'matched_peak', 'admitted_after', 'work']
    delta = {m: a[m] - b[m] for m in metrics}
    if mode == 'done':
        assert all(value == 0 for value in delta.values())
        assert b['transferred'] == 1
    else:
        assert b['transferred'] == 0 and delta['calls'] == -1
        assert delta['bytes'] == -(32*n-8)
        assert delta['finish_peak_admitted_delta'] == -32*n
        if n >= 1024:
            assert b['matched_peak'] == 3 and a['matched_peak'] == 2
            assert b['matched_allocations'] == 1 and a['matched_allocations'] == 0
            assert delta['requested_peak'] == -32*n
    pairs.append(dict(algorithm=key[0], local_vertices=n, mode=mode,
                      before=b, after=a, delta=delta))
result = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='PASS_ALL_18_MATCHED_PAIRS',
              scope='36 cells: one measured owner0, three configured partitions; n local vertices, sparse fixed arcs; no timing/RSS/cluster metric',
              baseline=dict(path=str(baseline.relative_to(ROOT)), sha256=sha(baseline)),
              candidate=dict(path=str(candidate.relative_to(ROOT)), sha256=sha(candidate)),
              admission_definition='Hold a normalization reservation so entry live=entry historical peak=64MiB. finish_peak_admitted_delta=exit cumulative peak-entry cumulative peak. This is a controlled incremental peak, not absolute live/admitted peak.',
              allocator_definition='calls/bytes count successful allocator requests during finish. requested_peak is max(0, cumulative allocated-request bytes minus all deallocated-request bytes) with zero at finish entry; seeded old/inbox pointers are separately watched for same-size storage overlap.',
              small_fixture_limit='n=1 same-size matched counters include metadata collisions; dense-label-only overlap assertions use n>=1024. Pointer transfer is checked for every size.',
              all_cells_retained=True, pairs=pairs)
(ROOT/'allocation-comparison.json').write_text(json.dumps(result, indent=2)+'\n')
print(result['outcome'])
