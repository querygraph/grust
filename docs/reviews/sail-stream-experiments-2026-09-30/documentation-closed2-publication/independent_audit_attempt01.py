"""Local-only independent publication review checks; writes outside candidate."""
from datetime import datetime, timezone
import ast
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/private/tmp/grust-sail-review-closed2-docs')
O = Path('/private/tmp/grust-sail-review-closed2-publication')
S = Path('/Users/alexy/src/grust')
E = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '7387b985f242164281c7d94a1560bbfcfa8d8fe5'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1 << 20): h.update(block)
    return h.hexdigest()


def info(path):
    assert path.is_file() and not path.is_symlink(), path
    return dict(sha256=sha(path), bytes=path.stat().st_size,
                mode=oct(path.stat().st_mode & 0o777))


def load(path):
    return json.loads(path.read_text())


def git(*args, root=R):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def shared_state():
    index = Path(git('rev-parse', '--path-format=absolute', '--git-path', 'index', root=S))
    return dict(head=git('rev-parse', 'HEAD', root=S), index=info(index),
                coordination=info(S/'codex-to-codex.md'),
                prose=info(S/E/'RESULTS.md'), response=info(S/E/'SEM-REVIEW-2-RESPONSE.md'))


def receipt_files(root, mapping):
    for name, expected in mapping.items():
        observed = info(root/name)
        assert all(observed[k] == v for k, v in expected.items() if k in observed), name


pin = load(O/'frozen.json')
prep = load(O/'preparation.json')
assert pin['tree'] == 'edff8c11be29a67a517b51eb7047a85364664b17'
assert pin['manifest_sha256'] == '74087795b283ce8ac746f11e755ae5b129f98e69070c867a64e6412bcc72e620'
assert sha(O/'preparation.json') == pin['preparation_sha256']
assert pin['base'] == BASE and git('rev-parse', 'HEAD') == BASE
assert subprocess.run(['git', '-C', str(R), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
assert git('write-tree') == pin['tree']
assert subprocess.run(['git', '-C', str(R), 'diff', '--quiet']).returncode == 0
assert not git('ls-files', '--others', '--exclude-standard')
assert sha(R/pin['manifest_path']) == pin['manifest_sha256']
before = dict(head=git('rev-parse', 'HEAD'), tree=git('write-tree'),
              manifest=sha(R/pin['manifest_path']), shared=shared_state())
assert before['shared'] == prep['shared_before'] == prep['shared_after']
assert len(prep['selected_sources']) == 214
for relative, expected in prep['selected_sources'].items():
    assert info(S/relative) == info(R/relative) == expected, relative

status = [line.split('\t') for line in git('diff', '--cached', '--name-status').splitlines()]
assert status == pin['staged_status']
assert len(status) == 159
modified = {path for kind, path in status if kind == 'M'}
assert modified == {'codex-to-codex.md', str(E/'DOCUMENTATION-SNAPSHOT.json'), str(E/'RESULTS.md'), str(E/'SEM-REVIEW-2-RESPONSE.md')}
added = [path for kind, path in status if kind == 'A']
assert len(added) == 155 and all(path.startswith(str(E)+'/') for path in added)
assert all(kind in {'A', 'M'} for kind, _ in status)
assert set(pin['allowlist']) == {path for _, path in status}
base_coord = subprocess.check_output(['git', '-C', str(R), 'show', BASE+':codex-to-codex.md'])
coord = (R/'codex-to-codex.md').read_bytes()
assert coord.startswith(base_coord)
append = coord[len(base_coord):].decode()
assert append.count('\n## ') == 1 and 'ACK closed Sail SSSP replay and input reference' in append

manifest = load(R/pin['manifest_path'])
old = json.loads(git('show', BASE+':'+pin['manifest_path']))
files = {row['path']: row for row in manifest['files']}
prior = {row['path']: row for row in old['files']}
assert len(files) == 2129 and len(prior) == 1974
assert set(prior) <= set(files)
changed_prior = {name for name in prior if files[name] != prior[name]}
assert changed_prior <= modified
assert len(set(files)-set(prior)) == 155
assert not any('/logging03/' in name or '/logging03-monitor/' in name for name in files)
assert all(not name.endswith(('.parquet', '.i64le', '.so', '.dylib')) for name in added)
assert 'private original Parquet' in ' '.join(manifest['pending_excluded_subtrees'])
assert manifest['generated_fixture_exclusions'] == old['generated_fixture_exclusions']
for row in manifest['files']:
    observed = info(R/row['path'])
    assert observed['sha256'] == row['sha256'] and observed['bytes'] == row['bytes']

# Verify new input/reference receipt chains and actual private file digests;
# no private bytes are copied and no dataset/kernel workload is rerun.
inp = R/E/'sem-review2/cit-patents-input-verification'
ir = load(inp/'receipt.json'); ia = load(inp/'independent-audit.json')
assert sha(inp/'receipt.json') == '56bb99e72d5b1c16bebc74e847d77d680131d58f5e03e6f10fb2f85b1123221e'
assert ia['receipt']['sha256'] == sha(inp/'receipt.json')
assert ia['outcome'] == 'PASS_INDEPENDENT_LOCAL_INPUT_AUDIT'
receipt_files(inp, ir['evidence_files'])
assert ia['vertex_rows'] == ir['vertices']['rows'] == 3774768
assert ia['edge_rows'] == ir['edges']['rows'] == 16518947
assert ir['vertices']['nulls'] == ir['vertices']['duplicate_rows_after_first'] == 0
assert ir['edges']['self_loops'] == 0 and ir['weight_column_present'] is False
assert ir['duplicate_edges'] == dict(measured=False, count=None)
private_hashes = {}
for item in ir['downloads']:
    path = Path(ir['private_original_directory'])/item['name']
    observed = info(path)
    assert observed['sha256'] == item['sha256'] and observed['bytes'] == item['bytes']
    private_hashes[item['name']] = {k: observed[k] for k in ('sha256', 'bytes')}

wcc = R/E/'sem-review2/cit-patents-wcc-reference'
wr = load(wcc/'run01/receipt.json'); build = load(wcc/'build02/build-receipt.json')
assert sha(wcc/'run01/receipt.json').startswith('e2352369')
assert wr['outcome'] == 'PASS_EXACT_WCC_REFERENCE_PREPARATION'
assert wr['input_receipt']['sha256'] == sha(inp/'receipt.json')
assert wr['build_receipt']['sha256'] == sha(wcc/'build02/build-receipt.json')
receipt_files(wcc, wr['source_files'])
assert wr['originals_before'] == wr['originals_after'] == private_hashes
assert wr['kernel']['component_count'] == wr['readback']['checks']['component_count'] == 3627
assert wr['kernel']['largest_component_vertices'] == wr['readback']['checks']['largest_component_vertices'] == 3764117
assert wr['kernel']['successful_unions'] + 3627 == 3774768
assert wr['reference_output']['sha256'] == 'b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc'
for identity in [wr['reference_output'], wr['binary']]:
    observed = info(Path(identity['path']))
    assert observed['sha256'] == identity['sha256'] and observed['bytes'] == identity['bytes']
assert load(wcc/'build01/build-receipt.json')['outcome'] == 'FAILED'
assert 'algorithm' in (wcc/'build01/compiler.log').read_text()
assert load(wcc/'independent-preparation-audit.json')['outcome'] == 'PASS_BOUNDED_INDEPENDENT_SOURCE_AND_BOUNDARY_REVIEW'
assert len(load(wcc/'independent-preparation-audit.json')['additional_controls']) == 2
controls = load(wcc/'build02/controls.json')
assert controls['valid_cases'] == 206 and controls['random_seed_count'] == 200
assert len(controls['expected_rejections']) == 6
assert all(x['returncode'] != 0 for x in controls['expected_rejections'])
assert sha(wcc/'build02/controls.json') == build['controls']['sha256']

# Closed logging02 outcome and evidence scope, distinct from still-active 03.
closed = load(R/E/'logging02/diagnostics/receipt.json')
assert closed['outcome'] == 'error'
assert load(R/E/'logging02/result.json')['outcome'] == 'oom'
assert 'oom_kill 2' in closed['cgroup_after']['memory.events']
first_fault = load(R/E/'logging02-first-fault-audit/analysis.json')
assert first_fault['outcome'] == 'LOGGING02_EXACT_CGROUP_WORKER_OOM_KILLS_CONFIRMED'
assert first_fault['cleanup']['post_shutdown_staging_inventory_present'] is False
assert [x['iteration'] for x in first_fault['iteration_events']] == [1, 1, 2]
assert (R/E/'logging02-monitor/serialized-read03-2107-summary.json').is_file()
assert (R/E/'logging02-monitor/serialized-read03-2107-summary-corrected.json').is_file()
assert (R/E/'logging02-monitor/observation-20260930T215856123740Z.json').is_file()

privacy = load(O/'independent-privacy-scan.json')
assert privacy['manifest_sha256'] == pin['manifest_sha256']
assert privacy['credential_pattern_matched_files'] == 0
gate_text = (O/'independent-documentation-gate.log').read_text()
assert gate_text.endswith('SAIL_REVIEW_DOCUMENTATION PASSED '+BASE+'\n')
gate = json.loads(gate_text[:gate_text.rindex('\nSAIL_REVIEW_DOCUMENTATION')])
assert gate['manifest_sha256'] == pin['manifest_sha256']
for name in ('guard.py', 'publish.py', 'independent_scan.py'):
    ast.parse((O/name).read_text())
subprocess.run(['/bin/sh', '-n', str(O/'commit_and_gate.sh')], check=True)
assert subprocess.run(['git', '-C', str(R), 'diff', '--cached', '--check']).returncode == 0
assert before == dict(head=git('rev-parse', 'HEAD'), tree=git('write-tree'),
                      manifest=sha(R/pin['manifest_path']), shared=shared_state())
for relative, expected in prep['selected_sources'].items():
    assert info(S/relative) == info(R/relative) == expected, relative

audit = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
    outcome='PASS_INDEPENDENT_PUBLICATION_AUDIT', repository='querygraph/grust',
    base_commit=BASE, frozen_index_tree=pin['tree'], manifest_sha256=pin['manifest_sha256'],
    selected_source_files_verified=214, changed_paths=159, new_paths=155,
    modified_prior_paths=sorted(modified), inherited_manifest_files=1974,
    total_manifest_files=2129, changed_prior_manifest_entries=sorted(changed_prior),
    gate=gate, privacy_scan=privacy, private_inputs_rehashed_without_copy=private_hashes,
    reference_receipt_sha256=sha(wcc/'run01/receipt.json'), reference_output=wr['reference_output'],
    prose_review=[
        'Closed logging02 OOM attribution names exact cgroup and both mapped worker victims, with original clock/sampling/cleanup limits. Earlier zero-OOM failures remain unresolved.',
        'Logging03 is admission/launch only; current cell, monitor and eventual result excluded. No compact performance result is claimed.',
        'Official cit-Patents byte/row preparation matches producer and independent bitmap receipts; no historical-byte, weight, duplicate-edge count or Stage A claim.',
        'WCC count/size and membership digest match the exact union-find receipt. Positive-ID bound, declared domain/isolates and sequential observed-memory controls are explicit; full readback is not a second independent WCC algorithm.',
        'Failed build01, failed observers, corrected optional-mapping summary and unfavorable earlier measurements remain retained. Only one task-specific coordination entry is appended.',
    ],
    control_review=[
        'guard.py binds frozen preparation, all 214 source hashes/sizes/modes, unchanged shared HEAD/index/prose/coordination, detached HEAD, index tree, manifest and independently pinned audit.',
        'commit_and_gate.sh is a single && chain: source guard, documentation gate, source guard, 16 closed-helper tests, 11 portable closure mocks, commit, exact-SHA guards/gate. No commit if a preceding command fails.',
        'publish.py requires clean exact gated direct child of base, matching frozen tree, both remote refs still at base, ancestry for each, atomic push with explicit per-ref CAS leases, then exact remote verification. It does not activate shared HEAD or rewrite working files.',
    ],
    control_sha256={name:sha(O/name) for name in ('guard.py','commit_and_gate.sh','publish.py','independent_scan.py','independent_audit.py')},
    limitations=[
        'Documentation publication audit only; no fresh Sail runtime, cluster, performance or Stage A qualification.',
        'No remote refs were read or written by this audit. Publisher remote checks remain required at delivery.',
        'Current privacy scan is heuristic and does not prove arbitrary secrets absent.',
        'I authored the earlier local first-fault audit; root independently reviewed it and Pecan separately sanity-checked its identity/clock/sampling limits. This publication pass independently checks candidate/source equality and receipt consistency, not a second independent first-fault discovery.',
        'No full input validator or WCC computation was rerun; actual private digests, source logic, receipts and controls were reviewed. Private originals/output were not copied.',
    ])
with (O/'independent-audit.json').open('x') as f:
    json.dump(audit, f, indent=2); f.write('\n')
print(json.dumps(dict(outcome=audit['outcome'], tree=pin['tree'], manifest=pin['manifest_sha256'], audit_sha256=sha(O/'independent-audit.json'))))
