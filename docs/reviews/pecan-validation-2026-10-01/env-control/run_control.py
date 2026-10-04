#!/usr/bin/env python3
"""Offline reproduction of installed-package shadowing; no SQL server."""
import ast
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
RUNNER = OUT.parent/'run_gate.py'
REPO = Path('/private/tmp/sail-pecan-validation-gate')
HEAD = 'cab6bacc0ad0d1fc8b3070e9e4267e99751909fe'
TREE = '51e9ae66d53e608fe08da54cd4ab91d750be0715'
GATE = runpy.run_path(str(RUNNER))
BASE = GATE['BASE']
SHA = BASE['sha']
START = BASE['utc']()
BEFORE = BASE['source_identity'](REPO, HEAD, TREE, 'candidate')
OLD_FAILURE = OUT.parent/'candidate-gate'
OLD_HASHES = {str(p.relative_to(OLD_FAILURE)): SHA(p) for p in OLD_FAILURE.rglob('*') if p.is_file()}
ORIGINAL = BASE['client_environment'](REPO/'examples/extensions/benchmarks', REPO)
CORRECTED = dict(ORIGINAL, PYTHONPATH=os.pathsep.join(map(str, [REPO/'examples/extensions/benchmarks',
    REPO/'examples/extensions/nutmeg/python', REPO/'examples/extensions/graph-algorithms/src', BASE['CLIENT']])))
for key in ('SAIL_GRAPH_TEST_REMOTE', 'GRAPH500_SOURCE', 'GRAPH500_MATRIX_GENERATOR', 'GAP_CONTROL_BINARY', 'PARALLEL_CONTROL_BINARY'):
    ORIGINAL.pop(key, None)
    CORRECTED.pop(key, None)
CORRECTED['PYTEST_ADDOPTS'] = ''
CORRECTED['CARGO_TARGET_DIR'] = str(OUT/'unused-target')
COMMANDS = []

def run(label, command, environment, expected):
    with (OUT/(label+'.log')).open('x') as stream:
        result = subprocess.run(command, cwd=REPO, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=90)
    COMMANDS.append(dict(label=label, command=command, returncode=result.returncode))
    assert (result.returncode == 0) == expected, label

ast.parse(RUNNER.read_text())
PYTHON = str(BASE['PYTHON'])
run('old-order-origin-rejected', [PYTHON, '-B', str(RUNNER), '--module-origin-probe', str(REPO)], ORIGINAL, False)
run('corrected-origin', [PYTHON, '-B', str(RUNNER), '--module-origin-probe', str(REPO)], CORRECTED, True)
TESTS = [
    'examples/extensions/argentea/python/test_argentea_sssp_client.py::test_wheel_manifest_advertises_only_explicit_worker_sssp_role',
    'examples/extensions/argentea/python/test_argentea_wcc_client.py::test_wheel_manifest_advertises_only_explicit_worker_wcc_role',
]
run('manifest-tests', [PYTHON, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--rootdir='+str(REPO),
    *TESTS, '--junitxml='+str(OUT/'manifest-tests.xml'), '--basetemp='+tempfile.mkdtemp(prefix='pecan-env-control-')], CORRECTED, True)
cases = ET.parse(OUT/'manifest-tests.xml').getroot().findall('.//testcase')
assert len(cases) == 2 and all(not list(case) for case in cases)
AFTER = BASE['source_identity'](REPO, HEAD, TREE, 'candidate')
assert BEFORE == AFTER
assert OLD_HASHES == {str(p.relative_to(OLD_FAILURE)): SHA(p) for p in OLD_FAILURE.rglob('*') if p.is_file()}
receipt = dict(outcome='PASS_SOURCE_PATH_ENV_CONTROL', started_utc=START, finished_utc=BASE['utc'](),
    head=HEAD, tree=TREE, source_unchanged=True, original_failed_gate_unchanged=True,
    old_runner_sha256=SHA(OUT/'run_gate-attempt01.py'), new_runner_sha256=SHA(RUNNER),
    original_pythonpath=ORIGINAL['PYTHONPATH'], corrected_pythonpath=CORRECTED['PYTHONPATH'],
    commands=COMMANDS, tests=dict(passed=2, skipped=0, failed=0),
    module_origins=json.loads((OUT/'corrected-origin.log').read_text()),
    original_failed_gate_hashes=OLD_HASHES,
    files_sha256={p.name: SHA(p) for p in OUT.iterdir() if p.is_file()},
    scope='Two existing manifest tests plus package-origin positive/negative controls only; no SQL/server/build.')
BASE['save'](OUT/'receipt.json', receipt)
print(json.dumps({k: receipt[k] for k in ('outcome', 'new_runner_sha256', 'tests')}))
