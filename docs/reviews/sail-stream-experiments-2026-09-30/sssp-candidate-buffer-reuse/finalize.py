"""Close reviewed, exact-gated component evidence without changing Sail refs."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

OUT = Path(__file__).parent
COMMIT = 'fc094a0c25a49edeac2f9f0195aa973421a21a43'
TREE = '5abc3e30eadb878402b3a90bcbeb0a48ac8c4b25'
BASE = '33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((OUT/name).read_text())


def git(repo, *command):
    return subprocess.check_output(['git', '-C', str(repo), *command],
                                   env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).decode().strip()


pin = read('frozen.json')
assert pin['base'] == BASE and pin['tree'] == TREE
for name in ('repo', 'gate'):
    root = Path(pin[name])
    assert git(root, 'rev-parse', 'HEAD') == COMMIT
    assert git(root, 'rev-parse', 'HEAD^{tree}') == TREE
    assert not git(root, 'status', '--porcelain')
    for path, digest in pin['paths'].items():
        assert sha(root/path) == digest
assert git(pin['repo'], 'rev-parse', 'HEAD^') == BASE
assert git(pin['repo'], 'symbolic-ref', '--short', 'HEAD') == pin['branch']
assert subprocess.run(['git', '-C', pin['gate'], 'symbolic-ref', '-q', 'HEAD'],
                      capture_output=True).returncode == 1
for kind, expected_head, exact in [('candidate-gate', BASE, False), ('exact-gate', COMMIT, True)]:
    receipt = read(kind+'/receipt.json')
    assert receipt['outcome'] == 'PASS' and receipt['head'] == expected_head
    assert receipt['tree'] == TREE and receipt['exact'] is exact
    assert receipt['script_sha256'] == pin['driver_sha256'] == sha(OUT/'run_gate.py')
    assert receipt['all_saturators_reaped'] and len(receipt['saturation']) == 10
    assert not (Path(receipt['target_root'])/'.sssp-candidate-gate.lock').exists()
    steps = {step['name']: step for step in receipt['steps']}
    for name in ('core-release', 'core-loaded'):
        assert steps[name]['tests_passed'] == 141
    for name in ('native-release', 'native-loaded'):
        assert steps[name]['tests_passed'] == 55 and steps[name]['argentea_tests_passed'] == 49
    for step in steps.values():
        assert step['outcome'] == 'PASS'
        assert sha(OUT/kind/step['log']) == step['log_sha256']
        if 'stderr_log' in step:
            assert sha(OUT/kind/step['stderr_log']) == step['stderr_log_sha256']
comparison = read('allocation-comparison.json')
assert comparison['outcome'] == 'PASS_ALL_18_MATCHED_PAIRS' and len(comparison['pairs']) == 18
assert read('baseline-source-proof.json')['outcome'] == 'PASS_UNCHANGED_PRODUCTION_BASELINE_AND_IDENTICAL_CONTROLS'
assert read('allocation-repeat-verification.json')['outcome'] == 'PASS_FORMAL_GATE_ALLOCATION_REPEATS'
audit = read('independent-review.json')
assert audit['outcome'] == 'PASS_INDEPENDENT_SSSP_REUSE_SOURCE_AND_GATE_AUDIT'
assert audit['commit'] == COMMIT and audit['tree'] == TREE
assert audit['readme_sha256'] == sha(OUT/'README.md')
assert audit['source_hashes'] == pin['paths']
for name, digest in audit['receipt_hashes'].items():
    path = OUT/name
    if path.is_dir():
        path = path/'receipt.json'
    assert sha(path) == digest
inputs = ['README.md', 'frozen.json', 'candidate.patch', 'baseline03/receipt.json',
          'candidate03/receipt.json', 'candidate-gate/receipt.json', 'exact-gate/receipt.json',
          'allocation-comparison.json', 'allocation-repeat-verification.json',
          'baseline-source-proof.json', 'independent-review.json', 'artifact-check.json']
receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='EXACT_COMPONENT_GATE_PASS',
               repository='querygraph/sail', branch=pin['branch'], base=BASE, commit=COMMIT, tree=TREE,
               candidate_gate='candidate-gate/receipt.json', exact_gate='exact-gate/receipt.json',
               core_tests=141, native_tests=55, native_argentea_tests=49, saturated_cores=10,
               allocation_cells=36, matched_pairs=18, source_files=len(pin['paths']),
               inputs={path: sha(OUT/path) for path in inputs},
               delivery='NOT_PUSHED_AT_EVIDENCE_CUTOFF',
               scope='Local requested allocations/admission, semantic/error/lease controls, core/native release gates. No timing/RSS/Linux/worker/Flight/host CLI/combined wheel/cluster qualification.')
with (OUT/'final-receipt.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
files = {str(path.relative_to(OUT)): sha(path) for path in sorted(OUT.rglob('*'))
         if path.is_file() and path.name != 'files-manifest.json'}
assert not any('__pycache__' in name for name in files)
with (OUT/'files-manifest.json').open('x') as stream:
    json.dump(dict(recorded_utc=datetime.now(timezone.utc).isoformat(), commit=COMMIT,
                   file_count=len(files), files=files), stream, indent=2)
    stream.write('\n')
print('EXACT_COMPONENT_GATE_PASS', COMMIT, 'files', len(files),
      'receipt', sha(OUT/'final-receipt.json'), 'manifest', sha(OUT/'files-manifest.json'))
