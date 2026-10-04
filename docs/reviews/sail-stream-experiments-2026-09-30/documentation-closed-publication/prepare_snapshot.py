"""Copy only explicitly closed evidence into an isolated detached docs snapshot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SRC = Path('/Users/alexy/src/grust')
DST = Path('/private/tmp/grust-sail-review-closed-docs')
OUT = Path('/private/tmp/grust-sail-review-closed-publication')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = 'f4443ba76c18c922698a060183c02ca65ce939c7'

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def info(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size, mode=oct(path.stat().st_mode & 0o777))

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

assert git(DST, 'rev-parse', 'HEAD') == BASE
assert not git(DST, 'status', '--porcelain')
index = Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
prose = ['RESULTS.md', 'SEM-REVIEW-2-RESPONSE.md', 'CLUSTER-PREPARATION.md']
def shared_state():
    return dict(head=git(SRC, 'rev-parse', 'HEAD'), index=info(index),
                coordination=info(SRC/'codex-to-codex.md'),
                prose={name: info(SRC/REL/name) for name in prose})
shared_before = shared_state()
directories = ['linux-builds', 'worker-smoke-compact561-cpu16-23', 'host-pair-16k',
               'cluster-ownership-control', 'documentation-followup-publication']
files = prose + ['audit_compact_worker_smoke.py', 'worker-smoke-561-admission.json',
                 'worker-smoke-561-identity-capture.json', 'preflight_cell.py',
                 'preflight-cell-staging.json', 'preflight-cell-independent-audit.json',
                 'documentation-followup-activation.json', 'logging02-admission.json']
selected = {REL / name for name in files}
excluded = []
excluded_parts = {'__pycache__', '.pytest_cache', 'pytest-temp', 'unit-temp', 'sql-temp'}
for name in directories:
    for path in (SRC/REL/name).rglob('*'):
        if not path.is_file():
            continue
        assert not path.is_symlink(), path
        relative = path.relative_to(SRC)
        if excluded_parts.intersection(relative.parts) or path.suffix == '.pyc':
            excluded.append(str(relative))
            continue
        selected.add(relative)
# Public catalog is an explicit twelve-file manifest plus its verification receipt.
catalog = SRC/REL/'sem-review2/input-catalog'
verification = json.loads((catalog/'verification.json').read_text())
assert verification['no_html_or_full_article_in_publication']
assert len(verification['public_files']) == 12
for name, expected in verification['public_files'].items():
    assert Path(name).name == name and not name.endswith('.html')
    assert sha(catalog/name) == expected['sha256']
    assert (catalog/name).stat().st_size == expected['bytes']
    selected.add(REL/'sem-review2/input-catalog'/name)
selected.add(REL/'sem-review2/input-catalog/verification.json')
assert not any('logging02-monitor' in r.parts or 'logging02-observations' in r.parts for r in selected)
assert json.loads((SRC/REL/'host-pair-16k/HANDOFF.json').read_text())['status'] == 'PREPARED_AND_STAGED_NOT_LAUNCHED'
original = json.loads((DST/REL/'DOCUMENTATION-SNAPSHOT.json').read_text())
mutable = {REL/name for name in prose} | {Path('codex-to-codex.md')}
before = {str(r): info(SRC/r) for r in sorted(selected)}
for relative in sorted(selected):
    destination = DST/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC/relative, destination)
assert before == {str(r): info(SRC/r) for r in sorted(selected)}, 'shared inputs changed while copying'
assert before == {str(r): info(DST/r) for r in sorted(selected)}, 'copy bytes or modes differ'
# Do not copy the shared checkout's unrelated coordination edits.
with (DST/'codex-to-codex.md').open('a') as stream:
    stream.write('\n\n## ' + datetime.now(timezone.utc).isoformat() + ' — Codex: ACK closed Sail evidence snapshot\n\n'
        'Repository `querygraph/grust`: freeze completed instrumented and compact Linux builds, scoped cache-cleanup receipts, compact worker correctness evidence, prepared-only weighted16k paired controls, cluster-ownership checks and the trimmed public input catalog. Preserve earlier failures and measurements. Logging02 is running at this snapshot; its active observations/cell remain excluded, compact scale24 has not started, and the paired study has not launched. Publication requires detached documentation gates and an independent audit. This is documentation integrity evidence, not a new runtime, release or performance verdict.\n')
for row in original['files']:
    if Path(row['path']) not in mutable:
        assert sha(DST/row['path']) == row['sha256'], 'prior tracked evidence altered: ' + row['path']
paths = {Path(row['path']) for row in original['files']} | selected | {Path('codex-to-codex.md')}
rows = [dict(path=str(r), sha256=sha(DST/r), bytes=(DST/r).stat().st_size) for r in sorted(paths)]
manifest = dict(original)
manifest.update(recorded_utc=datetime.now(timezone.utc).isoformat(), base_commit=BASE,
    publication_branches=['work/proposal-v5', 'work/sail-graph-review'],
    scope='Completed Linux builds and compact worker checks, prepared-only host comparison, cluster ownership and trimmed public input catalog. Logging02 is running at this snapshot; compact scale24 and paired measurements have not started. Documentation integrity only; no new runtime gate or performance verdict.',
    pending_excluded_subtrees=['logging02-monitor', 'logging02-observations', 'active logging02 actual-cell artifacts',
                              'generated fixtures and Python caches', 'private full third-party article/website/API originals'],
    excluded_file_count=len(excluded),
    excluded_file_count_scope='generated/cache files omitted within explicitly selected closed subtrees; active unselected and private files not enumerated',
    files=rows,
    source_copy_guard='All selected source bytes, sizes and modes matched before and after copying. Prior tracked evidence preserved except the three selected prose files and isolated appended coordination entry.')
write(DST/REL/'DOCUMENTATION-SNAPSHOT.json', manifest)
shared_after = shared_state()
assert shared_before == shared_after, 'shared checkout changed during preparation; inspect before proceeding'
write(OUT/'preparation.json', dict(recorded_utc=datetime.now(timezone.utc).isoformat(), repository='querygraph/grust',
    base_commit=BASE, worktree=str(DST), selected_directories=directories,
    selected_sources=before, excluded_generated_files=excluded, public_catalog_file_count=13,
    prior_manifest_files=len(original['files']), manifest_files=len(rows),
    manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'),
    shared_before=shared_before, shared_after=shared_after,
    scope='Only publication worktree edited; shared HEAD/index/prose/coordination untouched'))
print(json.dumps(dict(selected_files=len(selected), manifest_files=len(rows),
                     excluded_generated_files=len(excluded), manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'))))
