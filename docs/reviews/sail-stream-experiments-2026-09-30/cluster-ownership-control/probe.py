"""Public client admission checks and an exact ownership arithmetic control.

Does not execute Sail or claim measured scaling. The star model follows the
pinned source-owner rule, and is separate from the actual client calls.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    repo = args.repository.resolve()
    expected = '200d1cf8eb1db5e9057e09e071ebd57391f4b376'

    def git(*values):
        return subprocess.check_output(['git', '-C', str(repo), *values], text=True).strip()

    assert git('rev-parse', 'HEAD') == expected
    assert not git('status', '--porcelain')
    assert subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'],
                          capture_output=True).returncode == 1
    extension = repo / 'examples/extensions'
    for path in [extension / 'argentea/python', extension / 'nutmeg/python',
                 extension / 'graph-algorithms/src']:
        sys.path.insert(0, str(path))
    modules = {name: importlib.import_module(name) for name in [
        'argentea_client', 'argentea_delta_client', 'argentea_bfs_client',
        'argentea_sssp_client', 'argentea_wcc_client']}
    options = {
        'argentea_client': dict(iterations=1, reset_probability=0.15, batch_rows=4096),
        'argentea_delta_client': dict(max_pushes=1, reset_probability=0.15,
            tolerance=1e-6, max_phase_budget=32, batch_rows=4096),
        'argentea_bfs_client': dict(source=0, method='frontier', directed=False,
            max_levels=1, alpha=14, beta=24, max_phase_budget=32, batch_rows=4096),
        'argentea_sssp_client': dict(source=0, method='reference', max_rounds=1,
            delta=1.0, max_phase_budget=32, batch_rows=4096),
        'argentea_wcc_client': dict(method='reference', max_rounds=1, seed=42,
            max_phase_budget=32, batch_rows=4096),
    }
    checks = []
    for name, module in modules.items():
        assert Path(module.__file__).resolve().is_relative_to(repo)
        for partitions in [64, 65]:
            try:
                module.options(partitions=partitions, **options[name])
                result = dict(outcome='accepted')
            except ValueError as error:
                result = dict(outcome='rejected', error=str(error))
            assert result['outcome'] == ('accepted' if partitions == 64 else 'rejected')
            if partitions == 65:
                assert result['error'] == 'partitions must be an integer in 1..64'
            checks.append(dict(module=name, partitions=partitions, **result))

    owner_source = (extension / 'argentea/src/lib.rs').read_text()
    assert 'vertex.rem_euclid(self.partitions as i64) as usize' in owner_source
    vertices = 65536
    edges = vertices - 1
    cells = []
    for partitions in [1, 2, 4, 8, 16, 32, 64]:
        owned_vertices = [0] * partitions
        owned_arcs = [0] * partitions
        active_arcs = [0] * partitions
        for vertex in range(vertices):
            owned_vertices[vertex % partitions] += 1
        for leaf in range(1, vertices):
            owned_arcs[0] += 1       # center -> leaf
            owned_arcs[leaf % partitions] += 1  # leaf -> center
            active_arcs[0] += 1      # first frontier contains only the center
        assert len(set(owned_vertices)) == 1
        assert sum(owned_arcs) == 2 * edges
        assert owned_arcs[0] == edges + edges // partitions
        assert max(active_arcs) == sum(active_arcs) == edges
        cells.append(dict(partitions=partitions, vertices_per_owner=owned_vertices,
                          arcs_per_owner=owned_arcs, first_frontier_arcs_per_owner=active_arcs,
                          largest_arc_fraction=owned_arcs[0] / sum(owned_arcs),
                          active_work_sum_over_max=sum(active_arcs) / max(active_arcs)))

    sources = [Path(module.__file__) for module in modules.values()]
    sources += [extension / suffix for suffix in [
        'argentea/src/lib.rs', 'argentea/src/bfs/emission.rs',
        'nutmeg/src/argentea/request.rs', 'nutmeg/src/argentea/delta/request.rs',
        'nutmeg/src/argentea/bfs/request.rs', 'nutmeg/src/argentea/sssp/request.rs',
        'nutmeg/src/argentea/wcc/request.rs']]
    identities = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sources}
    assert git('rev-parse', 'HEAD') == expected and not git('status', '--porcelain')
    receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='passed',
                   source=expected, source_sha256=identities, client_checks=checks,
                   star=dict(vertices=vertices, undirected_input_edges=edges,
                             directed_arcs=2 * edges, source=0, cells=cells),
                   scope='actual Python option validation; separate source-derived exact ownership arithmetic, no native kernel, graph execution, timing, or cluster scaling measurement')
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'outcome': 'passed', 'client_checks': len(checks), 'star_cells': len(cells)}))


if __name__ == '__main__':
    main()
