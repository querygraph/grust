#!/usr/bin/env python3
"""Counterexample to the frozen benchmark WCC certificate's accepted predicates.

This is a relational predicate reproduction, not a Spark execution. PySpark and
Sail are unavailable in the review interpreter. The exact source assertions are
extracted below; SQLite evaluates their equivalents on a four-vertex fixture.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess


REPO = Path('/Users/alexy/src/sail-large-graphs')
COMMIT = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
FILE = 'examples/extensions/benchmarks/graph_cell.py'
source = subprocess.check_output(['git', '-C', str(REPO), 'show', f'{COMMIT}:{FILE}'], text=True)
function = next(node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name == 'certify')
wcc = next(node for node in function.body
           if isinstance(node, ast.If) and ast.unparse(node.test) == "algorithm == 'wcc'")
assertions = [ast.unparse(node.test) for node in ast.walk(wcc) if isinstance(node, ast.Assert)]

db = sqlite3.connect(':memory:')
db.executescript('''
CREATE TABLE vertices(id INTEGER PRIMARY KEY);
INSERT INTO vertices VALUES(0),(1),(2),(3);
CREATE TABLE edges(src INTEGER, dst INTEGER);
INSERT INTO edges VALUES(0,1),(2,3);
CREATE TABLE actual(id INTEGER, component TEXT);
INSERT INTO actual VALUES(0,'0'),(1,'0'),(2,'0'),(3,'0');
CREATE VIEW minima AS SELECT component AS label, MIN(id) AS minimum
  FROM actual GROUP BY component;
''')
scalar = lambda sql: db.execute(sql).fetchone()[0]
checks = {
    'rows': scalar('SELECT COUNT(*) FROM actual'),
    'unique_ids': scalar('SELECT COUNT(DISTINCT id) FROM actual'),
    'null_ids': scalar('SELECT COUNT(*) FROM actual WHERE id IS NULL'),
    'missing_vertices': scalar('SELECT COUNT(*) FROM vertices v WHERE NOT EXISTS '
                              '(SELECT 1 FROM actual a WHERE a.id=v.id)'),
    'null_labels': scalar('SELECT COUNT(*) FROM actual WHERE component IS NULL'),
    'crossing_edges': scalar('SELECT COUNT(*) FROM edges e JOIN actual s ON e.src=s.id '
                            'JOIN actual t ON e.dst=t.id WHERE s.component<>t.component'),
    'foreign_labels': scalar('SELECT COUNT(*) FROM minima m WHERE NOT EXISTS '
                            '(SELECT 1 FROM actual a WHERE CAST(m.label AS INTEGER)=a.id)'),
    'non_minimal_labels': scalar('SELECT COUNT(*) FROM minima '
                                'WHERE CAST(label AS INTEGER)<>minimum'),
    'reported_components': scalar('SELECT COUNT(*) FROM minima'),
}
assert checks == dict(rows=4, unique_ids=4, null_ids=0, missing_vertices=0,
                     null_labels=0, crossing_edges=0, foreign_labels=0,
                     non_minimal_labels=0, reported_components=1)
# Independent connected components of the undirected input.
adjacency = {i: set() for i in range(4)}
for src, dst in db.execute('SELECT src,dst FROM edges'):
    adjacency[src].add(dst)
    adjacency[dst].add(src)
components, unseen = [], set(adjacency)
while unseen:
    seen, todo = set(), [min(unseen)]
    while todo:
        vertex = todo.pop()
        if vertex not in seen:
            seen.add(vertex)
            todo.extend(adjacency[vertex] - seen)
    unseen -= seen
    components.append(sorted(seen))
assert components == [[0, 1], [2, 3]]
evidence = {
    'generated_utc': datetime.now(timezone.utc).isoformat(),
    'kind': 'counterexample to extracted accepted predicates; not a Spark integration test',
    'source': {'repo': str(REPO), 'commit': COMMIT, 'file': FILE,
               'sha256': hashlib.sha256(source.encode()).hexdigest(),
               'certificate_assertions': assertions},
    'input': {'vertices': list(range(4)), 'edges': [[0, 1], [2, 3]]},
    'corrupt_output': [[i, '0'] for i in range(4)],
    'observed_predicates': checks,
    'accepted_by_certificate_predicates': True,
    'actual_components': components,
    'actual_component_count': len(components),
    'reason': 'No edge crosses a reported label, but disconnected components may be merged. '
              'A connectedness witness for every label is absent.',
}
target = Path(__file__).with_suffix('.json')
target.write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'artifact': str(target), 'accepted': True, 'reported_components': 1,
                  'actual_components': 2}))
