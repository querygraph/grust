#!/usr/bin/env python3
"""Exercise the production executable against an independent Python BFS oracle."""
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys


def info(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def oracle(vertices, edges):
    neighbors = {v: set() for v in vertices}
    for source, target in edges:
        neighbors[source].add(target)
        neighbors[target].add(source)
    labels = {}
    for start in sorted(vertices):
        if start in labels:
            continue
        queue = deque([start]); labels[start] = start
        while queue:
            vertex = queue.popleft()
            for neighbor in neighbors[vertex]:
                if neighbor not in labels:
                    labels[neighbor] = start
                    queue.append(neighbor)
    return [(v, labels[v]) for v in sorted(vertices)]


def main():
    binary, private = Path(sys.argv[1]), Path(sys.argv[2])
    private.mkdir(exist_ok=False)
    binary_before = info(binary)
    cases = [('empty', [], []), ('all_isolates', [1, 7, 31], []),
             ('noncontiguous_two_components_and_isolate', [1, 3, 7, 11, 63], [(3, 1), (11, 7)]),
             ('duplicates_selfloops_reverse', [1, 2, 9, 27], [(9, 2), (2, 9), (9, 2), (1, 1), (27, 27)]),
             ('roots_not_minimum', [1, 2, 3, 4, 5, 6], [(6, 5), (6, 4), (6, 3), (2, 1), (6, 2)]),
             ('reverse_order', [63, 11, 7, 3, 1], [(7, 11), (1, 3)])]
    for seed in range(200):
        rng = random.Random(seed)
        vertices = rng.sample(range(1, 129), rng.randrange(0, 35))
        edges = [(rng.choice(vertices), rng.choice(vertices)) for _ in range(rng.randrange(0, 100))] if vertices else []
        if edges:
            edges.extend([edges[0], edges[0][::-1]])
        cases.append(('random_' + str(seed), vertices, edges))
    rows = []
    for name, vertices, edges in cases:
        folder = private/name; folder.mkdir()
        v, e, output = folder/'vertices.bin', folder/'edges.bin', folder/'membership.bin'
        v.write_bytes(b''.join(struct.pack('<q', x) for x in vertices))
        e.write_bytes(b''.join(struct.pack('<qq', *x) for x in edges))
        before = [info(v), info(e)]
        result = subprocess.run([str(binary), str(v), str(e), str(output), '1', '128', str(len(vertices)), str(len(edges)), 'positive-range-wcc-v1'], capture_output=True, text=True)
        assert result.returncode == 0, (name, result.stderr)
        stats = json.loads(result.stdout)
        actual = list(struct.iter_unpack('<qq', output.read_bytes()))
        expected = oracle(vertices, edges)
        assert actual == expected, (name, actual, expected)
        counts = Counter(label for _, label in expected)
        assert stats['component_count'] == len(counts)
        assert stats['largest_component_vertices'] == max(counts.values(), default=0)
        expected_min = min((label for label, size in counts.items() if size == stats['largest_component_vertices']), default=0)
        assert stats['largest_component_minimum_id'] == expected_min
        assert stats['output_rows'] == stats['vertex_rows'] == len(vertices)
        incident = {x for edge in edges for x in edge}
        assert stats['isolated_vertices_without_incident_edges'] == len(set(vertices)-incident)
        assert stats['singleton_components'] == sum(size == 1 for size in counts.values())
        assert stats['self_loop_edge_rows'] == sum(s == t for s, t in edges)
        assert before == [info(v), info(e)]
        rows.append(dict(name=name, vertex_rows=len(vertices), edge_rows=len(edges), component_count=len(counts), output=info(output)))
    rejected = []
    bad = [('duplicate_vertex', [1, 1], [], None), ('negative_id', [-1], [], None),
           ('outside_range', [129], [], None), ('missing_endpoint', [1], [(1, 2)], None),
           ('truncated_vertex', [1], [], 'vertex'), ('truncated_edge', [1], [(1, 1)], 'edge')]
    for name, vertices, edges, truncate in bad:
        folder=private/name; folder.mkdir();v=folder/'vertices.bin';e=folder/'edges.bin';output=folder/'membership.bin'
        v.write_bytes(b''.join(struct.pack('<q', x) for x in vertices));e.write_bytes(b''.join(struct.pack('<qq', *x) for x in edges))
        if truncate:
            path=v if truncate=='vertex' else e;path.write_bytes(path.read_bytes()[:-1])
        result=subprocess.run([str(binary),str(v),str(e),str(output),'1','128',str(len(vertices)),str(len(edges)),'positive-range-wcc-v1'],capture_output=True,text=True)
        assert result.returncode != 0 and not output.exists(), name
        rejected.append(dict(name=name, returncode=result.returncode, error=result.stderr.strip()))
    assert info(binary)==binary_before
    print(json.dumps(dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_PRODUCTION_KERNEL_BFS_CONTROLS',binary=binary_before,valid_cases=len(rows),random_seed_count=200,expected_rejections=rejected,cases=rows,scope='Same production executable and file parser, including sparse IDs, isolates, loops, duplicates and reversed edges. Python BFS uses independent adjacency sets/queue. No timing assertions.'),indent=2))


if __name__ == '__main__':
    main()
