"""Source-derived arithmetic/graph controls only; no SQL server or graph engine."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
SAIL = Path('/Users/alexy/src/sail-large-graphs')
SHA = 'fc094a0c25a49edeac2f9f0195aa973421a21a43'
FILES = [
    'examples/extensions/benchmarks/traversal_certificate.py',
    'examples/extensions/benchmarks/traversal_cell.py',
    'examples/extensions/benchmarks/test_traversal_certificate.py',
    'examples/extensions/benchmarks/graph_cell.py',
    'examples/extensions/graph-algorithms/src/pyspark_pecan/traversal.py',
    'examples/extensions/graph-algorithms/src/pyspark_pecan/traversal_stepping.py',
    'examples/extensions/argentea/python/argentea_sssp_client.py',
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(SAIL), *args])


def distances(edges, root=0):
    result = {root: 0}
    queue = deque([root])
    while queue:
        u = queue.popleft()
        for a, b in edges:
            if a == u and b not in result:
                result[b] = result[u] + 1
                queue.append(b)
    return result


def parent_valid(edges, reached, parents, hops, n=3):
    if parents[0] != 0 or hops[0] != 0:
        return False
    for v in reached - {0}:
        p = parents[v]
        if p not in reached or type(hops[v]) is not int or not 1 <= hops[v] < n:
            return False
        if hops[v] != hops[p] + 1 or (p, v) not in edges:
            return False
    return True


def arithmetic(u, w, v, tolerance):
    candidate = u + w
    allowed = ((tolerance + tolerance * abs(u)) + tolerance * abs(w)) + tolerance * abs(v)
    old_residual = abs((v - u) - w)
    old_allowed = 1e-12 * (1 + abs(v))
    return {'source_distance': u, 'weight': w, 'target_distance': v,
            'tolerance': tolerance, 'candidate': candidate, 'allowed': allowed,
            'certificate_residual': abs(v - candidate),
            'certificate_tight': abs(v - candidate) <= allowed,
            'old_parent_residual': old_residual, 'old_parent_allowed': old_allowed,
            'old_parent_accepts': old_residual <= old_allowed}


def main():
    started = datetime.now(timezone.utc).isoformat()
    assert git('rev-parse', SHA + '^{commit}').decode().strip() == SHA
    sources = {}
    for name in FILES:
        data = git('show', SHA + ':' + name)
        sources[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    containing_refs = git('branch', '-r', '--contains', SHA).decode().splitlines()
    assert any('querygraph/' in ref for ref in containing_refs)
    # Exhaustive three-vertex graphs include self-loops and disconnected zero cycles.
    possible = list(itertools.product(range(3), repeat=2))
    tested = valid = 0
    for edge_mask in range(1 << len(possible)):
        edges = {edge for i, edge in enumerate(possible) if edge_mask & (1 << i)}
        for extra_mask in range(4):
            reached = {0} | {i + 1 for i in range(2) if extra_mask & (1 << i)}
            # Preserve the current all-edge reachability-closure prerequisite.
            if any(u in reached and v not in reached for u, v in edges):
                continue
            rest = sorted(reached - {0})
            for selected_parents in itertools.product(sorted(reached), repeat=len(rest)):
                for selected_hops in itertools.product([1, 2], repeat=len(rest)):
                    parents = {0: 0, **dict(zip(rest, selected_parents))}
                    hops = {0: 0, **dict(zip(rest, selected_hops))}
                    tested += 1
                    if parent_valid(edges, reached, parents, hops):
                        valid += 1
                        witness = distances(edges)
                        assert reached <= set(witness)
                        assert all(witness[v] <= hops[v] <= 2 for v in reached)
    differing_acceptance = arithmetic(1.0, 1.0, 2.0 + 4e-12, 1e-12)
    assert differing_acceptance['certificate_tight'] and not differing_acceptance['old_parent_accepts']
    regrouping = arithmetic(1.0, 2.0 ** -53, 1.0, 0.0)
    assert regrouping['certificate_residual'] == 0 and regrouping['old_parent_residual'] > 0
    # Exact same tight graph can have a longer declared parent path than BFS depth.
    edges = {(0, 1), (1, 2), (0, 2)}
    parents = {0: 0, 1: 0, 2: 1}
    hops = {0: 0, 1: 1, 2: 2}
    assert parent_valid(edges, {0, 1, 2}, parents, hops)
    assert max(distances(edges).values()) == 1 and max(hops.values()) == 2
    # A disconnected zero-weight cycle cannot have positive integer hops +1 locally.
    assert not parent_valid({(1, 2), (2, 1)}, {0, 1, 2}, {0: 0, 1: 2, 2: 1}, {0: 0, 1: 1, 2: 2})
    # SQL WHERE keeps only TRUE; a negated equality with NULL does not reject a row.
    comparison_with_missing_parent = None
    naive_invalid_where_keeps_row = comparison_with_missing_parent is True
    explicit_null_guard_keeps_row = True
    assert not naive_invalid_where_keeps_row and explicit_null_guard_keeps_row
    report = {
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'started_utc': started,
        'outcome': 'SOURCE_DERIVED_PARENT_WITNESS_CONTROLS_PASS', 'sail_commit': SHA,
        'containing_remote_refs': [s.strip() for s in containing_refs], 'sources': sources,
        'exhaustive_control': {'vertices': 3, 'directed_graphs': 512,
            'graph_reached_parent_hop_cases': tested, 'valid_parent_witness_cases': valid,
            'weights': 'all zero; all finite reached distances zero; absent vertices unreachable',
            'property': 'Every accepted total integer parent/hop proof reaches the root via existing tight edges; BFS depth never exceeds supplied hops.'},
        'predicate_acceptance_counterexample': differing_acceptance,
        'floating_regrouping_counterexample': regrouping,
        'round_cap_counterexample': {'edges': sorted(edges), 'parents': parents, 'hops': hops,
            'bfs_witness_rounds': 1, 'maximum_parent_hops': 2, 'cap': 1,
            'consequence': 'Rejecting because parent hops exceed cap would reject an existing BFS-certificate pass; use existing BFS fallback in that case to preserve outcomes.'},
        'sql_null_control': {'engine_executed': False, 'comparison_with_missing_parent': None,
            'naive_invalid_where_keeps_row': naive_invalid_where_keeps_row,
            'explicit_null_guard_keeps_row': explicit_null_guard_keeps_row,
            'scope': 'Three-valued SQL semantics only, not an actual Sail SQL observation.'},
        'limits': ['No Sail source modified, implementation, compilation, SQL endpoint, workload or timing experiment.',
            'Three-vertex enumeration supports the stated mathematical induction; it does not qualify an implementation.',
            'Float expressions reproduced with Python binary64 in source order; actual SQL/DataFusion expression evaluation requires a later implementation gate.',
            'Keep the existing parent numeric predicate as an additional condition if existing parent-output acceptance must remain identical.'],
        'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with (OUT / 'receipt.json').open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(report['outcome'], tested, valid)


if __name__ == '__main__':
    main()
