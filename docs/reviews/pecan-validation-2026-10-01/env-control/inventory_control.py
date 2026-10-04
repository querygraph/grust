#!/usr/bin/env python3
"""Match corrected collection identities to all retained JUnit cases; no tests run."""
from collections import Counter
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess

from _pytest.junitxml import mangle_test_address

OUT = Path(__file__).resolve().parent
RUNNER = OUT.parent/'run_gate.py'
GATE = runpy.run_path(str(RUNNER))
BASE = GATE['BASE']
REPO = Path('/private/tmp/sail-pecan-validation-gate-02')
HEAD = 'cab6bacc0ad0d1fc8b3070e9e4267e99751909fe'
TREE = '5e87eb7a730646168c0f0cb6db989c4573a06e18'
FAILED = OUT.parent/'candidate-gate-02'
BEFORE = BASE['source_identity'](REPO, HEAD, TREE, 'candidate')
HASHES = {p.name: BASE['sha'](p) for p in FAILED.iterdir() if p.is_file()}
START = BASE['utc']()
ENV = BASE['client_environment'](REPO/'examples/extensions/benchmarks', REPO)
ENV['PYTHONPATH'] = os.pathsep.join(map(str, [REPO/'examples/extensions/benchmarks',
    REPO/'examples/extensions/nutmeg/python', REPO/'examples/extensions/graph-algorithms/src', BASE['CLIENT']]))
ENV['PYTEST_ADDOPTS'] = ''
for key in ('SAIL_GRAPH_TEST_REMOTE', 'GRAPH500_SOURCE', 'GRAPH500_MATRIX_GENERATOR', 'GAP_CONTROL_BINARY', 'PARALLEL_CONTROL_BINARY'):
    ENV.pop(key, None)
CMD = [str(BASE['PYTHON']), '-B', str(RUNNER), '--collect', str(REPO)]
result = subprocess.run(CMD, cwd=REPO, env=ENV, capture_output=True, text=True, timeout=120)
with (OUT/'inventory-corrected-collection.log').open('x') as file:
    file.write(result.stdout)
with (OUT/'inventory-corrected-collection.stderr').open('x') as file:
    file.write(result.stderr)
assert result.returncode == 0
rows = json.loads(result.stdout)['items']
assert len(rows) == 1473
for row in rows:
    assert row['classname'] == '.'.join(mangle_test_address(row['nodeid'])[:-1])
xml = FAILED/'offline.xml'
counts = GATE['xml_result'](xml, rows, True)
assert {k: counts[k] for k in ('tests', 'passed', 'skipped', 'errors', 'failures')} == dict(
    tests=1473, passed=1237, skipped=236, errors=0, failures=0)
old = json.loads((FAILED/'inventory.json').read_text())['items']
changed = [(a, b) for a, b in zip(old, rows) if a != b]
assert len(changed) == 1 and changed[0][0]['nodeid'] == changed[0][1]['nodeid']
assert set(k for k in changed[0][0] if changed[0][0][k] != changed[0][1][k]) == {'classname'}
controls = []
mutated = copy.deepcopy(rows)
mutated[0]['name'] += '-incorrect'
for name, data in [('original-bug', old), ('missing', rows[1:]), ('duplicate', rows+[rows[0]]), ('mismatched', mutated)]:
    try:
        GATE['xml_result'](xml, data, True)
    except AssertionError as error:
        controls.append(dict(case=name, outcome='REJECTED', reason=str(error)))
    else:
        raise AssertionError(name+' was accepted')
assert BEFORE == BASE['source_identity'](REPO, HEAD, TREE, 'candidate')
assert HASHES == {p.name: BASE['sha'](p) for p in FAILED.iterdir() if p.is_file()}
receipt = dict(outcome='PASS_EXACT_JUNIT_INVENTORY_CONTROL', started_utc=START, finished_utc=BASE['utc'](),
    head=HEAD, tree=TREE, source_unchanged=True, original_failed_gate_unchanged=True,
    old_runner_sha256=BASE['sha'](OUT/'inventory-oldrunner.py'), runner_sha256=BASE['sha'](RUNNER),
    command=CMD, counts={k: counts[k] for k in ('tests', 'passed', 'skipped', 'errors', 'failures')},
    all_classnames_match_pytest_reporter=True, corrected_identity=changed[0], negative_controls=controls,
    original_failed_gate_hashes=HASHES,
    scope='New collection matched against prior actual 1473-case JUnit and four rejecting identity mutations. No test/service/build rerun.')
BASE['save'](OUT/'inventory-control-receipt.json', receipt)
print(json.dumps({k: receipt[k] for k in ('outcome', 'runner_sha256', 'counts', 'negative_controls')}, indent=2))
