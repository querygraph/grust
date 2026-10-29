"""Independent integer-only reader for the one exported Java profile."""
import bisect
import json
from pathlib import Path

root = Path(__file__).resolve().parent
report = json.loads((root / 'java-portable-cycle-proof.json').read_text())
profile = report['profile']
historical = profile['explicit_transitions']
cycle = profile['future_cycle']
times = [row[0] for row in historical]
cycle_times = [row[0] for row in cycle]
assert all(a < b for a, b in zip(times, times[1:]))
assert all(a < b for a, b in zip(cycle_times, cycle_times[1:]))
assert cycle_times[0] == 0
assert cycle_times[-1] < profile['future_cycle_period_millis']

def offset(millis):
    if millis < times[0]:
        return profile['raw_prefix_offset_millis']
    if millis <= times[-1]:
        return historical[bisect.bisect_right(times, millis)-1][1]
    mapped = (millis-profile['future_cycle_anchor_millis']) % profile['future_cycle_period_millis']
    return cycle[bisect.bisect_right(cycle_times, mapped)-1][1]

for row in report['boundary_cases']:
    micros = row['input_micros']
    millis = micros // 1000
    assert offset(millis) == row['offset_millis']
    utc_to_la = -offset(millis-offset(millis))
    assert utc_to_la == row['utc_to_la_adjustment_millis']
    assert offset(millis) == row['la_to_utc_adjustment_millis']
    value = micros + utc_to_la*1000
    assert str(value) == row['utc_to_la_result_micros']
    assert (-2**63 <= value < 2**63) == row['utc_to_la_result_fits_i64']

result = {'scope': 'Independent integer-only Python profile reader versus retained public Java oracle boundary rows',
          'passed_cases': len(report['boundary_cases']), 'failed_cases': 0,
          'profile_zone': profile['zone'], 'future_cycle_rows': len(cycle),
          'historical_rows': len(historical)}
(root / 'portable-cycle-verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
