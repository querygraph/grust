#!/usr/bin/env python3
"""Bounded read-only source/predicate/consumer controls; no Sail server executed."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

REPO = Path('/private/tmp/sail-stream-review-integrated')
COMMIT = 'b569e75de625885b3d919fa4196b2e0bed14c618'
ROOT = REPO / 'examples/extensions/benchmarks'
assert subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
assert not subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True)
sys.path.insert(0, str(ROOT))
import run_matrix
import summarize
from test_summarize import records

source = (ROOT / 'graph_cell.py').read_text()
parsed = ast.parse(source)
certify = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == 'certify')
wcc = next(n for n in certify.body if isinstance(n, ast.If) and ast.unparse(n.test) == "algorithm == 'wcc'")
assertions = [ast.unparse(n.test) for n in ast.walk(wcc) if isinstance(n, ast.Assert)]
assert len(assertions) == 3

vertices = list(range(4)); edges = [(0, 1), (2, 3)]
expected = {0: 0, 1: 0, 2: 2, 3: 2}  # Two independently enumerated connected components.
def predicate_case(name, components):
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE vertices(id INTEGER); CREATE TABLE edges(src INTEGER,dst INTEGER); CREATE TABLE actual(id INTEGER,component TEXT);')
    db.executemany('INSERT INTO vertices VALUES(?)', [(v,) for v in vertices])
    db.executemany('INSERT INTO edges VALUES(?,?)', edges)
    db.executemany('INSERT INTO actual VALUES(?,?)', list(enumerate(components)))
    db.execute('CREATE VIEW minima AS SELECT component AS label,MIN(id) AS minimum FROM actual GROUP BY component')
    scalar = lambda q: db.execute(q).fetchone()[0]
    checks = dict(rows=scalar('SELECT COUNT(*) FROM actual'), unique_ids=scalar('SELECT COUNT(DISTINCT id) FROM actual'),
        null_ids=scalar('SELECT COUNT(*) FROM actual WHERE id IS NULL'),
        missing_vertices=scalar('SELECT COUNT(*) FROM vertices v WHERE NOT EXISTS(SELECT 1 FROM actual a WHERE a.id=v.id)'),
        null_labels=scalar('SELECT COUNT(*) FROM actual WHERE component IS NULL'),
        crossing_edges=scalar('SELECT COUNT(*) FROM edges e JOIN actual s ON s.id=e.src JOIN actual d ON d.id=e.dst WHERE s.component<>d.component'),
        foreign_labels=scalar('SELECT COUNT(*) FROM minima m WHERE NOT EXISTS(SELECT 1 FROM actual a WHERE CAST(m.label AS INTEGER)=a.id)'),
        labels_not_in_own_group=scalar('SELECT COUNT(*) FROM minima m WHERE NOT EXISTS(SELECT 1 FROM actual a WHERE CAST(m.label AS INTEGER)=a.id AND m.label=a.component)'),
        reported_components=scalar('SELECT COUNT(*) FROM minima'))
    canonical = {i: min(j for j in vertices if components[j] == components[i]) for i in vertices}
    accepted = checks['rows'] == checks['unique_ids'] == 4 and all(checks[k] == 0 for k in ('null_ids','missing_vertices','null_labels','crossing_edges','foreign_labels'))
    db.close()
    return dict(name=name, labels=components, predicates=checks, original_certificate_predicates_accept=accepted,
                exact_reference_partition_accept=canonical == expected)
cases = [predicate_case('correct_partition', ['0','0','2','2']),
         predicate_case('merged_disconnected_components', ['0','0','0','0']),
         predicate_case('representatives_in_other_group', ['2','2','0','0']),
         predicate_case('split_connected_components', ['0','1','2','3'])]
assert [(x['original_certificate_predicates_accept'],x['exact_reference_partition_accept']) for x in cases] == [(True,True),(True,False),(True,True),(False,False)]
assert cases[1]['predicates']['labels_not_in_own_group'] == 0
assert cases[2]['predicates']['labels_not_in_own_group'] == 2
record = dict(transport_errors=[], attach_returncode=1, inspect={'state': {'OOMKilled': False}})
receipt = dict(harness_source_sha='a'*40, outcome='partially_verified', correctness={'policy':'certificate','component_count_verified':False})
classification = run_matrix.classify(record,receipt,'a'*40)
assert classification == 'partially_verified'
oom = deepcopy(record); oom['inspect']['state']['OOMKilled'] = True
assert run_matrix.classify(oom,receipt,'a'*40) == 'oom'
config, entries = records()
for cell, summary, trial in entries:
    cell['algorithm'] = summary['algorithm'] = trial['arguments']['algorithm'] = 'wcc'
    trial['arguments']['ranking_validation'] = 'certificate'
    trial['correctness'] = {'policy':'certificate','component_count_verified':False}
rows = summarize.audited_rows(entries, config)
assert all(r['outcome'] == 'passed' and not r['integrity_errors'] for r in rows)
legacy, = summarize.aggregate(rows)
assert legacy['passed'] == 3 and legacy['metrics']['seconds']['samples'] == 3
partial_entries = deepcopy(entries)
for cell, summary, trial in partial_entries:
    summary['outcome'] = trial['outcome'] = 'partially_verified'
partial_rows = summarize.audited_rows(partial_entries, config)
partial, = summarize.aggregate(partial_rows)
assert partial['passed'] == 0 and partial['outcomes'] == {'partially_verified':3}
assert all(m is None for m in partial['metrics'].values())
assert all(r['seconds'] == 5 for r in partial_rows)
files = ['graph_cell.py','run_matrix.py','summarize.py','test_summarize.py']
result = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), repository=str(REPO), commit=COMMIT,
    scope='SQLite reproduction of four integer-label predicates plus actual Python classify/audited_rows/aggregate functions; no Spark/Sail server, no remote workload, no timing claim',
    source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
    extracted_certificate_assertions=assertions, fixture={'vertices':vertices,'edges':edges,'reference_components':[[0,1],[2,3]]}, cases=cases,
    downstream={'new_partial_receipt_exit_1_classification':classification,'oom_overrides_partial':'oom',
        'legacy_passed_partial_certificate_integrity_errors':[r['integrity_errors'] for r in rows],
        'legacy_passed_partial_certificate_aggregate':legacy,
        'explicit_partial_aggregate':partial,'explicit_partial_per_cell_seconds_retained':[r['seconds'] for r in partial_rows]}, verdict='All bounded controls reproduced expected current behavior')
output=Path(__file__).with_name('probe-result.json');output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'verdict':result['verdict'],'source':COMMIT,'cases':len(cases),'legacy_false_pass_samples':legacy['passed'],'explicit_partial_pass_samples':partial['passed'],'artifact':str(output)}))
