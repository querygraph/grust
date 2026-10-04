"""Exact-arithmetic counterexample for the two proposed ten-step PR contracts.

This evaluates recurrences read from the pinned implementations; it does not
execute either engine or measure performance. Vertices 0 and 1 form a directed
cycle, and vertex 2 is isolated. All values use rational arithmetic.
"""
from datetime import datetime, timezone
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path


def main():
    damping, reset = Q(17, 20), Q(3, 20)
    power = [Q(1, 3)] * 3
    accumulated = [reset] * 3
    delta = [reset] * 3
    active = [True] * 3
    edges = [(0, 1), (1, 0)]
    for _ in range(10):
        incoming = [Q(0)] * 3
        for source, target in edges:
            incoming[target] += power[source]
        dangling = power[2]
        power = [reset / 3 + damping * (value + dangling / 3)
                 for value in incoming]
        messages = [Q(0)] * 3
        for source, target in edges:
            if active[source]:
                messages[target] += delta[source]
        delta = [damping * value for value in messages]
        accumulated = [rank + change for rank, change in zip(accumulated, delta)]
        active = [change > Q(1, 100) for change in delta]
    normalized_delta = [rank / sum(accumulated) for rank in accumulated]
    assert sum(power) == sum(normalized_delta) == 1
    # Independent closed forms for the isolated coordinate in this fixture.
    stationary_isolate = Q(3, 43)
    assert power[2] == stationary_isolate + (Q(1, 3) - stationary_isolate) * (damping / 3) ** 10
    assert accumulated == [1 - damping ** 11, 1 - damping ** 11, reset]
    difference = sum(abs(a - b) for a, b in zip(power, normalized_delta))
    assert difference > Q(1, 100), 'counterexample must materially differ'
    def values(vector):
        return [{'exact': str(value), 'decimal': float(value)} for value in vector]
    result = {
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'kind': 'source-derived recurrence control; not an engine run',
        'source_commits': {
            'sail': 'b569e75de625885b3d919fa4196b2e0bed14c618',
            'graphframes_rs_source': 'b4da56dabe20bba8e29563e06acc5179b2113ce3',
            'graphframes_rs_results': 'ba2fdd8f51fa7fafdca15012d2741f5f8d80c024',
        },
        'vertices': [0, 1, 2], 'directed_edges': edges, 'iterations': 10,
        'power_with_dangling_redistribution': values(power),
        'normalized_delta_with_0_01_participation': values(normalized_delta),
        'l1_difference': {'exact': str(difference), 'decimal': float(difference)},
        'conclusion': 'equal iteration counts do not define equal finite-step outputs',
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
