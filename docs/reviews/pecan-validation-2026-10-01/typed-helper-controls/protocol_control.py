"""Positive and refuting synthetic controls for paired action evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import runpy
import tempfile
from typing import Any

OUT = Path(__file__).resolve().parent
P = runpy.run_path(str(OUT.parent/'typed_action_probe.py'))
PRIVATE = Path(tempfile.mkdtemp(prefix='typed-action-protocol-control-'))
Site, Action = P['Site'], P['Action']
events: list[Any] = []
for site in [*[Site('algorithms.py', '_snapshot', 1, 'if vertices.where(...)')]*5,
             Site('algorithms.py', '_snapshot', 2, 'return vertices, edges, vertices.count()'),
             Site('traversal.py', 'body', 3, 'vertices.where(source).count()'),
             Site('traversal.py', 'body', 4, 'edges.where(weight).count()'),
             Site('staging.py', 'materialize', 5, 'stored.count()'),
             *[Site('traversal_relaxation.py', 'materialize_weighted_relaxation', 6, 'overflow = stored.count()')]*3]:
    index = len(events)
    events.extend([Action(index, 'count', 'algorithm', None, [site]),
                   Action(index+1, 'ExecutePlan', 'algorithm', index),
                   Action(index+2, 'count_return', 'algorithm', index)])
for _ in range(20):
    events.append(Action(len(events), 'ExecutePlan', 'algorithm', None))
old_actions = P['actions'](events)
new_actions = P['actions']([Action(i, 'ExecutePlan', 'algorithm', None) for i in range(20)])
assert old_actions['count_calls'] == 12 and old_actions['execute_plan_calls'] == 32
assert new_actions['count_calls'] == 0 and new_actions['execute_plan_calls'] == 20
for label, malformed in [('missing-forward', events[:1]+events[2:]), ('missing-return', events[:2]+events[3:])]:
    try:
        P['actions'](malformed)
    except RuntimeError:
        pass
    else:
        raise AssertionError(label)
base = dict(outcome='PASS_EXACT_ORACLE', session_closed=True, source_unchanged=True, converged=True,
            spark_version='4.0.1', runtime_claim='pinned', endpoint={'host':'localhost','port':1},
            rows=[list(row) for row in P['EXPECTED']], iterations=3)
old = dict(base, label='baseline', actions=old_actions)
new = dict(base, label='candidate', actions=new_actions)
results = []


def trial(name: str, candidate: dict[str, Any], success: bool) -> None:
    folder = PRIVATE/name
    (folder/'baseline').mkdir(parents=True)
    (folder/'candidate').mkdir()
    for label, value in [('baseline', old), ('candidate', candidate)]:
        (folder/label/'receipt.json').write_text(json.dumps(value))
    try:
        P['compare'](folder/'baseline', folder/'candidate', folder/'comparison.json')
    except RuntimeError as error:
        assert not success, error
        results.append(dict(case=name, outcome='REJECTED', reason=str(error)))
    else:
        assert success, name
        results.append(dict(case=name, outcome='PASS'))


trial('exact-pair', new, True)
for name, key, value in [('false-convergence','converged',False), ('cleanup-failure','session_closed',False),
                         ('different-runtime','runtime_claim','other'), ('iteration-change','iterations',4)]:
    trial(name, dict(new, **{key:value}), False)
wrong = copy.deepcopy(new)
wrong['rows'][2][3] = 42
trial('wrong-parent', wrong, False)
wrong = copy.deepcopy(new)
wrong['actions']['count_calls'] = 1
wrong['actions']['count_categories'] = {'source_membership':1}
trial('retained-audit-count', wrong, False)
wrong = copy.deepcopy(new)
wrong['actions']['execute_plan_calls'] += 1
trial('unexplained-execute-plan', wrong, False)
print(json.dumps(dict(outcome='PASS_SYNTHETIC_ACTION_PROTOCOL', controls=results,
    missing_forward_and_return_rejected=True, scope='Synthetic only; no engine/session/process created.'), indent=2))
