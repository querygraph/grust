"""Bind the conditional integration commit to the completed detached union gate."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = Path('/private/tmp/sail-stream-review-followup')
GATE = Path('/private/tmp/sail-resource-validation-union-gate')
MAIN_SHA = 'ac1b12fbe08ac290b862c4453431fe31f95ef3d61b9ba27506b1f1c0ee6c1bdd'
SQL_SHA = '0aca81a5819f29095d2592804aea836250d7640de917ce7d959a264ec80f124e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True,
                                   env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).strip()


prep = json.loads((ROOT/'source-preparation.json').read_text())
gate_path = ROOT/'candidate-gate02/receipt.json'
gate = json.loads(gate_path.read_text())
assert gate['outcome'] == 'PASS' and gate['head'] == prep['base'] and gate['tree'] == prep['tree']
assert gate['exact'] is False and gate['repo'] == str(GATE)
assert gate['script_sha256'] == MAIN_SHA == sha(ROOT/'run_gate.py')
assert gate['sql_helper_sha256'] == SQL_SHA == sha(ROOT/'sql_gate.py')
assert not (Path(gate['target_root'])/'.resource-validation-gate.lock').exists()
assert gate['all_saturators_reaped'] and gate['saturation']
assert len(gate['saturation']) == os.cpu_count()
assert all(row['reaped'] and row['group_cleanup']['group_absent'] for row in gate['cleanup'])
steps = {s['name']: s for s in gate['steps']}
expected = ['diff-check', 'host-format', 'host-clippy', 'host-tests', 'core-format',
            'core-clippy', 'native-changed-format', 'core-release', 'native-build',
            'native-registry', 'native-release',
            'core-loaded', 'native-loaded', 'cli-build', 'python-sql']
assert len(steps) == len(gate['steps']) and list(steps) == expected
for step in steps.values():
    assert step['outcome'] == 'PASS' and step['returncode'] == 0
    assert sha(gate_path.parent/step['log']) == step['log_sha256']
    if 'stderr_log' in step:
        assert sha(gate_path.parent/step['stderr_log']) == step['stderr_log_sha256']
    assert step['process_cleanup']['leader_reaped'] and step['process_cleanup']['group_absent']
registry_path = gate_path.parent/'native-registry.json'
registry = json.loads(registry_path.read_text())
registry_sha = sha(registry_path)
assert gate['native_registry'] == dict(registry, registry_sha256=registry_sha)
assert registry['tests'] == 51 and registry['argentea_tests'] == 45
assert len(registry['names']) == len(set(registry['names'])) == 51
assert sum(name.startswith('argentea::') for name in registry['names']) == 45
assert sha(Path(registry['binary'])) == registry['binary_sha256']
assert registry['registry_log_sha256'] == steps['native-registry']['log_sha256']
for name, count in [('host-tests', 77), ('core-release', 120), ('core-loaded', 120),
                    ('native-release', 51), ('native-loaded', 51)]:
    assert steps[name]['tests_passed'] == count
for name in ('native-release', 'native-loaded'):
    assert steps[name]['argentea_tests_passed'] == 45
    assert steps[name]['summaries'] == [[51, 0, 0, 0, 0]]
    assert steps[name]['native_registry_sha256'] == registry_sha
    assert steps[name]['native_binary_sha256'] == registry['binary_sha256']
for name in ('core-loaded', 'native-loaded'):
    assert steps[name]['load_alive_before'] == steps[name]['load_alive_after'] == len(gate['saturation'])
child_path = gate_path.parent/'sql/receipt.json'
assert sha(child_path) == gate['sql_receipt_sha256']
child = json.loads(child_path.read_text())
assert child['outcome'] == 'passed' and child['source_and_runtime_unchanged'] and child['server_reaped']
assert child['unit_tests'] == dict(tests=430, failures=0, errors=0, skipped=97)
assert child['sql_tests'] == dict(tests=58, failures=0, errors=0, skipped=0)
assert sha(Path(gate['binary']['path'])) == gate['binary']['sha256']
frozen = json.loads((gate_path.parent/'source-before.json').read_text())
assert sha(gate_path.parent/'source-before.json') == gate['source_before_sha256']
for root in (REPO, GATE):
    assert git(root, 'rev-parse', 'HEAD') == prep['base']
    assert git(root, 'write-tree') == prep['tree']
    assert not git(root, 'diff', '--name-only')
    assert not git(root, 'ls-files', '--others', '--exclude-standard')
    for name, pin in frozen['files'].items():
        path = root/name
        value = (hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
                 if path.is_symlink() else sha(path))
        assert value == pin['sha256'] and path.lstat().st_mode == pin['mode'], name
assert git(REPO, 'symbolic-ref', '--short', 'HEAD') == 'work/stream-review-followup'
merge_path = Path(git(REPO, 'rev-parse', '--git-path', 'MERGE_HEAD'))
if not merge_path.is_absolute():
    merge_path = REPO/merge_path
assert set(merge_path.read_text().splitlines()) == set(prep['components'])
receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='PASS_COMMIT_GUARD',
               base=prep['base'], tree=prep['tree'], components=prep['components'],
               candidate_gate_sha256=sha(gate_path), sql_receipt_sha256=sha(child_path),
               driver_sha256=sha(Path(__file__)), binary=gate['binary'])
with (ROOT/'candidate-commit-guard.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print('RESOURCE_VALIDATION_COMMIT_GUARD PASS '+prep['tree'])
