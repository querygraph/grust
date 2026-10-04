"""Activate an already published exact snapshot without overwriting unrelated edits."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SRC = Path('/Users/alexy/src/grust')
DST = Path('/private/tmp/grust-sail-review-closed2-docs')
OUT = Path('/private/tmp/grust-sail-review-closed2-publication')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '7387b985f242164281c7d94a1560bbfcfa8d8fe5'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def info(path):
    return dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                mode=oct(path.stat().st_mode & 0o777))


delivery = json.loads((OUT/'delivery.json').read_text())
assert delivery['verdict'] == 'DELIVERED_EXACT_DOCUMENTATION_GATE_PASS'
receipt_path = SRC/REL/'documentation-closed2-activation.json'
assert not receipt_path.exists()
assert not (OUT/'activation-intent.json').exists()
assert not (OUT/'activation-failure.json').exists()
head = delivery['commit']
assert git(DST, 'rev-parse', 'HEAD') == head and not git(DST, 'status', '--porcelain')
assert git(DST, 'rev-parse', 'HEAD^') == BASE
assert git(SRC, 'rev-parse', 'HEAD') == BASE
assert git(SRC, 'symbolic-ref', 'HEAD') == 'refs/heads/work/proposal-v5'
assert subprocess.run(['git', '-C', str(SRC), 'diff', '--cached', '--quiet']).returncode == 0
refs = ['refs/heads/work/proposal-v5', 'refs/heads/work/sail-graph-review']
actual = {line.split()[1]: line.split()[0] for line in git(SRC, 'ls-remote', 'origin', *refs).splitlines()}
assert actual == dict.fromkeys(refs, head)
prep = json.loads((OUT/'preparation.json').read_text())
for name, expected in prep['selected_sources'].items():
    assert info(SRC/name) == expected == info(DST/name), name
manifest = REL/'DOCUMENTATION-SNAPSHOT.json'
old_manifest = subprocess.check_output(['git', '-C', str(SRC), 'show', BASE + ':' + str(manifest)])
assert (SRC/manifest).read_bytes() == old_manifest
old_coord = subprocess.check_output(['git', '-C', str(SRC), 'show', BASE + ':codex-to-codex.md'])
new_coord = (DST/'codex-to-codex.md').read_bytes()
current_coord = (SRC/'codex-to-codex.md').read_bytes()
# Only the isolated candidate must append to BASE. The shared log contains
# pre-existing insertions preserved by earlier publications; retain its entire
# captured byte sequence and append, without interpreting or rewriting it.
assert new_coord.startswith(old_coord)
appendix = new_coord[len(old_coord):]
assert appendix and appendix not in current_coord
dirty = git(SRC, 'diff', '--name-only').splitlines()
preserved = set(prep['selected_sources']) | set(dirty)
preserved -= {'codex-to-codex.md', str(manifest)}
before = {name: info(SRC/name) for name in preserved}
index = Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
index_before = info(index)
backup = Path(tempfile.mkdtemp(prefix='grust-closed2-activation-', dir='/private/tmp'))
shutil.copy2(index, backup/'index')
(backup/'coordination.md').write_bytes(current_coord)
(backup/'manifest.json').write_bytes(old_manifest)
temporary_index = backup/'new-index'
env = dict(os.environ, GIT_INDEX_FILE=str(temporary_index))
subprocess.run(['git', '-C', str(SRC), 'read-tree', head], env=env, check=True)
new_manifest = backup/'new-manifest.json'
shutil.copy2(DST/manifest, new_manifest)
lock = index.with_name(index.name + '.lock')
intent = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), base_commit=BASE,
              commit=head, private_backup=str(backup), index_before=index_before,
              coordination_before=info(SRC/'codex-to-codex.md'),
              helper=info(Path(__file__)))
with (OUT/'activation-intent.json').open('x') as stream:
    json.dump(intent, stream, indent=2)
    stream.write('\n')
phase = 'prepared'
try:
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        assert git(SRC, 'symbolic-ref', 'HEAD') == 'refs/heads/work/proposal-v5'
        assert git(SRC, 'rev-parse', 'HEAD') == BASE and info(index) == index_before
        assert (SRC/'codex-to-codex.md').read_bytes() == current_coord
        assert (SRC/manifest).read_bytes() == old_manifest
        assert before == {name: info(SRC/name) for name in preserved}
        subprocess.run(['git', '-C', str(SRC), 'update-ref', 'refs/heads/work/proposal-v5', head, BASE], check=True)
        phase = 'branch_updated'
        os.replace(temporary_index, index)
        phase = 'index_installed'
        os.replace(new_manifest, SRC/manifest)
        phase = 'manifest_installed'
        with (SRC/'codex-to-codex.md').open('ab') as stream:
            stream.write(appendix)
        phase = 'coordination_appended'
    finally:
        os.close(fd)
        lock.unlink()
    assert git(SRC, 'symbolic-ref', 'HEAD') == 'refs/heads/work/proposal-v5'
    assert git(SRC, 'rev-parse', 'HEAD') == head
    assert subprocess.run(['git', '-C', str(SRC), 'diff', '--cached', '--quiet']).returncode == 0
    assert before == {name: info(SRC/name) for name in preserved}
    assert (SRC/manifest).read_bytes() == (DST/manifest).read_bytes()
    assert (SRC/'codex-to-codex.md').read_bytes().startswith(current_coord + appendix)
    phase = 'postconditions_checked'
    recorded = datetime.now(timezone.utc).isoformat()
    with (SRC/'codex-to-codex.md').open('a') as stream:
        stream.write('\n\n## ' + recorded + ' — Codex: DONE closed Sail evidence publication\n\n'
        'Repository `querygraph/grust`: both `work/proposal-v5` and `work/sail-graph-review` now name `' + head + '`; exact verdict `SAIL_REVIEW_DOCUMENTATION PASSED ' + head + '`. The closed SSSP replay records both mapped workers OOM-killed; the historical zero-OOM failures and operator allocation site remain unexplained. Official cit-Patents input and exact WCC-reference receipts are retained. This snapshot includes only logging03 admission and launch; its final compact outcome and performance qualification are excluded. Shared index/branch activation preserved unrelated edits and all selected source bytes; only the new snapshot manifest and isolated coordination append were applied.\n')
    phase = 'done_appended'
    assert (SRC/'codex-to-codex.md').read_bytes().startswith(current_coord + appendix)
    receipt = dict(recorded_utc=recorded, repository='querygraph/grust', base_commit=BASE, commit=head,
    private_backup=str(backup), preserved_source_paths=len(preserved), preserved_source_hashes=before,
    remote_verified=actual, index_matches_head=True, unrelated_edits_preserved=True,
    shared_status=git(SRC, 'status', '--short', '--untracked-files=no'),
    source='Guarded temporary-index/ref CAS activation; no reset, checkout, blanket add or unrelated-file rewrite.')
    with receipt_path.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    phase = 'success_receipt_written'
except BaseException as error:
    failure = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
                   last_completed_phase=phase, private_backup=str(backup),
                   base_commit=BASE, commit=head, error=repr(error),
                   automatic_rollback=False)
    for label, args in [('head', ('rev-parse', 'HEAD')), ('branch', ('symbolic-ref', 'HEAD'))]:
        try:
            failure[label] = git(SRC, *args)
        except Exception as state_error:
            failure[label + '_read_error'] = repr(state_error)
    with (OUT/'activation-failure.json').open('x') as stream:
        json.dump(failure, stream, indent=2)
        stream.write('\n')
    raise
print(json.dumps(dict(commit=head, preserved_paths=len(preserved), backup=str(backup), status=receipt['shared_status'])))
