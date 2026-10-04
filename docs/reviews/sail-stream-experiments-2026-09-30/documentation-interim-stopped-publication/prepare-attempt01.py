"""Freeze closed interim observations; never copy a running cell or live writer."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SRC = Path('/Users/alexy/src/grust')
DST = Path('/private/tmp/grust-sail-review-interim-docs')
OUT = Path('/private/tmp/grust-sail-review-interim-publication')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = 'b478e57cb34220c1f671dca7ce92b2b061867855'
CUTOFF_FILE = 'observation-20260930T205638787925Z.json'
CUTOFF = datetime.fromisoformat('2026-09-30T20:57:33.709595+00:00')

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def info(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size, mode=oct(path.stat().st_mode & 0o777))

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

assert git(DST, 'rev-parse', 'HEAD') == BASE and not git(DST, 'status', '--porcelain')
assert git(SRC, 'rev-parse', 'HEAD') == BASE
for ref in ('origin/work/proposal-v5', 'origin/work/sail-graph-review'):
    assert git(SRC, 'rev-parse', ref) == BASE
index = Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
def shared_state():
    return dict(head=git(SRC, 'rev-parse', 'HEAD'), index=info(index),
                coordination=info(SRC/'codex-to-codex.md'), prose=info(SRC/REL/'RESULTS.md'))
shared_before = shared_state()
directories = ['logging03-prelaunch-audit', 'sampler-observation-audit',
               'scheduler-starvation-source-audit', 'documentation-closed-publication']
selected = {REL/'RESULTS.md', REL/'documentation-closed-activation.json'}
excluded = []
for name in directories:
    for path in (SRC/REL/name).rglob('*'):
        if not path.is_file():
            continue
        assert not path.is_symlink()
        relative = path.relative_to(SRC)
        if '__pycache__' in relative.parts or path.suffix == '.pyc':
            excluded.append(dict(path=str(relative), reason='Python cache'))
        else:
            selected.add(relative)
monitor = SRC/REL/'logging02-monitor'
observations = []
for path in sorted(monitor.iterdir()):
    relative = path.relative_to(SRC)
    if not path.is_file():
        excluded.append(dict(path=str(relative), reason='directory or active/cache state outside explicit file scope'))
        continue
    assert not path.is_symlink()
    if path.name == 'serialized-monitor-results.jsonl':
        excluded.append(dict(path=str(relative), reason='live append-only observer ledger, not a closed snapshot input'))
        continue
    if path.suffix == '.pyc':
        excluded.append(dict(path=str(relative), reason='Python cache'))
        continue
    if path.name.startswith('observation-'):
        if path.name > CUTOFF_FILE:
            excluded.append(dict(path=str(relative), reason='observation after frozen cutoff'))
            continue
        value = json.loads(path.read_text())
        assert 'local_finished_utc' in value, 'in-flight observer file: ' + path.name
        assert datetime.fromisoformat(value['local_finished_utc']) <= CUTOFF
        observations.append(dict(file=path.name, local_finished_utc=value['local_finished_utc'],
                                 failed=value.get('returncode') is None))
    elif path.suffix == '.json':
        value = json.loads(path.read_text())
        timestamp = value.get('local_finished_utc') or value.get('finished_utc') or value.get('recorded_utc')
        if timestamp:
            assert datetime.fromisoformat(timestamp) <= CUTOFF, 'closed record after cutoff: ' + path.name
    else:
        assert path.suffix in ('.py', '.md'), path.name
    selected.add(relative)
assert observations[-1]['file'] == CUTOFF_FILE
assert sum(row['failed'] for row in observations) == 8
assert all(REL/'logging02-monitor'/name in selected for name in ['observer-loop-stop.json', 'observer-loop-stop02.json'])
before = {str(path): info(SRC/path) for path in sorted(selected)}
original = json.loads((DST/REL/'DOCUMENTATION-SNAPSHOT.json').read_text())
for relative in sorted(selected):
    destination = DST/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC/relative, destination)
assert before == {str(path): info(SRC/path) for path in sorted(selected)}
assert before == {str(path): info(DST/path) for path in sorted(selected)}
with (DST/'codex-to-codex.md').open('a') as stream:
    stream.write('\n\n## ' + datetime.now(timezone.utc).isoformat() + ' — Codex: ACK interim Sail documentation snapshot\n\n'
        'Repository `querygraph/grust`: preserve the completed local configuration, sampler and runtime-source audits and closed supplemental observations through the logging02 observation collected at 2026-09-30T20:57:33.709595Z. All eight failed observer reads and both local stop attempts remain retained. Logging02 remains active: this is interim diagnostic evidence, not a completed replay or performance qualification. The full running cell, live observer ledger, later observations and Python caches remain excluded. Publication requires detached documentation gates, independent privacy/source review and an exact-commit gate; shared HEAD, index and prose are not activated by the publisher.\n')
mutable = {REL/'RESULTS.md', Path('codex-to-codex.md')}
for row in original['files']:
    if Path(row['path']) not in mutable:
        assert sha(DST/row['path']) == row['sha256'], 'prior evidence altered: ' + row['path']
paths = {Path(row['path']) for row in original['files']} | selected | {Path('codex-to-codex.md')}
rows = [dict(path=str(path), sha256=sha(DST/path), bytes=(DST/path).stat().st_size) for path in sorted(paths)]
manifest = dict(original)
manifest.update(recorded_utc=datetime.now(timezone.utc).isoformat(), base_commit=BASE,
    publication_branches=['work/proposal-v5', 'work/sail-graph-review'],
    scope='Interim logging02 observations and completed source/configuration/sampler audits. Replay remains active, no final replay result or performance qualification; compact replay and paired measurements have not started. Documentation integrity only.',
    frozen_observation_cutoff=dict(file='logging02-monitor/'+CUTOFF_FILE,
                                  remote_finished_utc='2026-09-30T20:57:33.058643+00:00',
                                  local_finished_utc=CUTOFF.isoformat()),
    observation_history_note='The observer README is dated through the stopped-loop/one-shot state at20:52. The later closed20:55 serialized authorization and20:57 observation are also retained; their still-running ledger is excluded.',
    pending_excluded_subtrees=['full running logging02 actual-cell output', 'logging02-monitor/serialized-monitor-results.jsonl',
                              'future or in-flight logging02 observations after the frozen cutoff', '__pycache__ and generated fixtures',
                              'private full third-party article/website/API originals'],
    excluded_file_count=len(excluded),
    excluded_file_count_scope='Explicit exclusions encountered in newly selected follow-up directories only; inherited exclusions remain separate; future/unselected/private files not exhaustively enumerated.',
    files=rows,
    source_copy_guard='Selected source bytes/sizes/modes matched before and after copying. Prior tracked evidence is unchanged except current root RESULTS copied verbatim and one isolated coordination append. No candidate-only prose differences.')
write(DST/REL/'DOCUMENTATION-SNAPSHOT.json', manifest)
shared_after = shared_state()
assert shared_before == shared_after, 'shared state changed during preparation; stop and inspect'
write(OUT/'preparation.json', dict(recorded_utc=datetime.now(timezone.utc).isoformat(), repository='querygraph/grust',
    base_commit=BASE, worktree=str(DST), selected_directories=directories,
    selected_sources=before, excluded_files=excluded, observations=observations,
    failed_observations=8, local_stop_attempts_retained=2,
    prior_manifest_files=len(original['files']), manifest_files=len(rows),
    manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'),
    shared_before=shared_before, shared_after=shared_after,
    candidate_only_prose_differences=[], scope='Only detached worktree edited; shared state preserved.'))
print(json.dumps(dict(selected_files=len(selected), observation_files=len(observations),
    failed_observations=8, manifest_files=len(rows), excluded_files=excluded,
    manifest_sha256=sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'))))
