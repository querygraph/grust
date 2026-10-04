"""Freeze completed logging02 evidence and input preparation, preserving prior bytes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SRC = Path('/Users/alexy/src/grust')
DST = Path('/private/tmp/grust-sail-review-closed2-docs')
OUT = Path('/private/tmp/grust-sail-review-closed2-publication')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '7387b985f242164281c7d94a1560bbfcfa8d8fe5'
REFS = ['refs/heads/work/proposal-v5', 'refs/heads/work/sail-graph-review']


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def info(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size, mode=oct(path.stat().st_mode & 0o777))


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


assert git(DST, 'rev-parse', 'HEAD') == BASE and not git(DST, 'status', '--porcelain')
assert git(SRC, 'rev-parse', 'HEAD') == BASE
for ref in REFS:
    assert git(SRC, 'rev-parse', ref.replace('refs/heads/', 'origin/')) == BASE
index = Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))


def shared_state():
    return dict(head=git(SRC, 'rev-parse', 'HEAD'), index=info(index),
                coordination=info(SRC/'codex-to-codex.md'), prose=info(SRC/REL/'RESULTS.md'),
                response=info(SRC/REL/'SEM-REVIEW-2-RESPONSE.md'))


before_shared = shared_state()
directories = ['logging02', 'logging02-monitor', 'logging02-observations',
               'logging02-first-fault-audit', 'closed-cell-audit',
               'host-closure-collector-review', 'documentation-interim-publication',
               'sem-review2/cit-patents-input-verification',
               'sem-review2/cit-patents-wcc-reference']
files = ['RESULTS.md', 'SEM-REVIEW-2-RESPONSE.md', 'collect_host_closure.py',
         'documentation-interim-activation.json', 'logging02-collection.json',
         'logging02-host-closure.json', 'logging03-admission01.json', 'logging03-launch.json']
selected = {REL / name for name in files}
excluded = []
for name in directories:
    directory = SRC/REL/name
    assert directory.is_dir(), name
    for path in directory.rglob('*'):
        assert not path.is_symlink(), str(path)
        if not path.is_file():
            continue
        relative = path.relative_to(SRC)
        if '__pycache__' in relative.parts or path.suffix == '.pyc':
            excluded.append(dict(path=str(relative), reason='Python cache'))
            continue
        assert path.suffix not in ('.parquet', '.bin', '.so', '.dylib', '.exe'), str(path)
        selected.add(relative)

# These closed records are required; an active/missing cell cannot become a verdict.
cell = json.loads((SRC/REL/'logging02/result.json').read_text())
assert cell['outcome'] == 'oom' and cell['receipt_outcome'] == 'error'
audit = json.loads((SRC/REL/'closed-cell-audit/logging02-verification.json').read_text())
assert audit['integrity_status'] == 'integrity_verified'
reference = json.loads((SRC/REL/'sem-review2/cit-patents-wcc-reference/run01/receipt.json').read_text())
assert reference['outcome'] == 'PASS_EXACT_WCC_REFERENCE_PREPARATION'
assert reference['kernel']['component_count'] == 3627
assert (SRC/REL/'logging02-monitor/serialized-six-2143-stopped-receipt.json').is_file()
assert (SRC/REL/'logging02-first-fault-audit/artifact-manifest.json').is_file()

before = {str(path): info(SRC/path) for path in sorted(selected)}
original = json.loads((DST/REL/'DOCUMENTATION-SNAPSHOT.json').read_text())
for relative in sorted(selected):
    destination = DST/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC/relative, destination)
assert before == {str(path): info(SRC/path) for path in sorted(selected)}
assert before == {str(path): info(DST/path) for path in sorted(selected)}
with (DST/'codex-to-codex.md').open('a') as stream:
    stream.write('\n\n## ' + datetime.now(timezone.utc).isoformat() + ' — Codex: ACK closed Sail SSSP replay and input reference\n\n'
        'Repository `querygraph/grust`: retain the completed logging02 SSSP replay, exact-cgroup kernel kills of both mapped workers, first-fault chronology and all observer/collection failures. Preserve the new official cit-Patents input hashes and exact WCC reference, including failed build attempts and correctness controls. Logging03 has started after matched fresh admission; only its fixed launch/admission records enter this snapshot. Its running cell/monitor and later matched measurements are excluded. Documentation gates and independent review must pass on the detached candidate and exact commit before atomic publication. No runtime release, historical zero-OOM diagnosis, operator allocation-site attribution or end-to-end performance qualification is claimed.\n')
mutable = {REL/'RESULTS.md', REL/'SEM-REVIEW-2-RESPONSE.md', Path('codex-to-codex.md')}
for row in original['files']:
    if Path(row['path']) not in mutable:
        assert sha(DST/row['path']) == row['sha256'], 'prior evidence altered: ' + row['path']
paths = {Path(row['path']) for row in original['files']} | selected | {Path('codex-to-codex.md')}
rows = [dict(path=str(path), sha256=sha(DST/path), bytes=(DST/path).stat().st_size) for path in sorted(paths)]
manifest = dict(original)
manifest.update(recorded_utc=datetime.now(timezone.utc).isoformat(), base_commit=BASE,
    publication_branches=['work/proposal-v5', 'work/sail-graph-review'],
    scope='Closed logging02 worker OOM evidence and local official-input/WCC-reference preparation; logging03 launch/admission only. Documentation integrity, not a completed compact replay, engine comparison or scaling result.',
    frozen_observation_cutoff=dict(file='logging02-monitor/observation-20260930T215856123740Z.json',
                                  state='Logging02 observer series stopped after confirmed remote exit; no observer remains. Full closed cell and original sampler/log are now included.'),
    observation_history_note='Earlier observer README/summaries retain their original dated interim scope. All later completed logging02 observations, failure receipts and the now-closed ledger are retained; final classification comes from the collected cell and first-fault audit.',
    pending_excluded_subtrees=['running logging03 full cell and logging03-monitor', 'future paired16k measurements',
                              '__pycache__ and generated fixtures', 'private original Parquet, binary reference files/executables, full SSH/kernel output and third-party pages'],
    excluded_file_count=len(excluded), excluded_file_count_scope='Explicit cache exclusions in new selected directories only; private and unselected sources are not exhaustively enumerated.',
    files=rows, source_copy_guard='Selected source bytes/sizes/modes matched before and after copying; prior evidence unchanged except current root RESULTS/SEM response and one isolated coordination append. No candidate-only prose differences.')
(DST/REL/'DOCUMENTATION-SNAPSHOT.json').write_text(json.dumps(manifest, indent=2)+'\n')
assert before_shared == shared_state(), 'shared state changed during preparation'
write(OUT/'preparation.json', dict(recorded_utc=datetime.now(timezone.utc).isoformat(), repository='querygraph/grust',
    base_commit=BASE, worktree=str(DST), expected_remote_refs=dict.fromkeys(REFS, BASE), selected_directories=directories,
    selected_sources=before, excluded_files=excluded, prior_manifest_files=len(original['files']), manifest_files=len(rows),
    manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'), shared_before=before_shared, shared_after=shared_state(),
    candidate_only_prose_differences=[], scope='Only detached candidate edited; active logging03 and shared state excluded/preserved.'))
print(json.dumps(dict(selected_files=len(selected), manifest_files=len(rows), manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'))))
