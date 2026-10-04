"""Activate only the already-published exact snapshot; preserve unrelated bytes.

Coordination may gain suffixes after preparation. The shared log is never
replaced by the candidate log; existing historical insertions remain intact.
Partial failure retains a private backup and phase, never automatic rollback.
"""
import shutil
import tempfile
from common import *

phase = 'preconditions'
backup = None
head = None
fd = None
lock = None
receipt_path = SRC/REL/'documentation-validation-activation.json'
check(not receipt_path.exists() and not (OUT/'activation-intent.json').exists()
      and not (OUT/'activation-failure.json').exists(), 'activation already attempted')
try:
    pin = load(OUT/'frozen.json')
    prep = load(OUT/'preparation.json')
    delivery = load(OUT/'delivery.json')
    check(delivery['verdict'] == 'DELIVERED_EXACT_DOCUMENTATION_GATE_PASS', 'not delivered')
    head = delivery['commit']
    subprocess.run(['python3', str(OUT/'guard.py'), 'exact-before', head], check=True, env=ENV)
    actual_remote_refs = remote_refs()
    check(actual_remote_refs == dict.fromkeys(REFS, head), 'actual published refs differ')
    check_shared(prep)
    check(subprocess.run(['git', '-C', str(SRC), 'diff', '--cached', '--quiet'], env=ENV).returncode == 0,
          'staged shared edits')
    old_manifest = git_bytes(SRC, 'show', BASE+':'+str(MANIFEST))
    check((SRC/MANIFEST).read_bytes() == old_manifest, 'shared snapshot manifest changed')
    base_coord = git_bytes(SRC, 'show', BASE+':'+str(COORD))
    candidate_coord = (DST/COORD).read_bytes()
    check(candidate_coord.startswith(base_coord), 'candidate coordination must append to base')
    appendix = candidate_coord[len(base_coord):]
    check(info(DST/COORD)['bytes'] > len(base_coord), 'empty candidate coordination appendix')
    check(dict(bytes=len(appendix), sha256=sha_bytes(appendix)) == prep['coordination_appendix'], 'appendix changed')
    current_coord = (SRC/COORD).read_bytes()
    check(appendix not in current_coord, 'candidate appendix already exists in shared log')
    current_prefix = dict(bytes=len(current_coord), sha256=sha_bytes(current_coord))
    dirty = set(git(SRC, 'diff', '--name-only').splitlines())
    preserved = (set(prep['selected_sources']) | dirty | {str(x) for x in REVIEW_INPUTS}) - {str(COORD), str(MANIFEST)}
    before = {name: info(SRC/name) for name in preserved}
    index = index_path()
    index_before = info(index)
    backup = Path(tempfile.mkdtemp(prefix='grust-validation-activation-', dir='/private/tmp'))
    shutil.copy2(index, backup/'index')
    (backup/'coordination-before-lock.md').write_bytes(current_coord)
    (backup/'manifest.json').write_bytes(old_manifest)
    temporary_index = backup/'new-index'
    index_env = dict(ENV, GIT_INDEX_FILE=str(temporary_index))
    subprocess.run(['git', '-C', str(SRC), 'read-tree', head], env=index_env, check=True)
    check(subprocess.check_output(['git', '-C', str(SRC), 'write-tree'], env=index_env).decode().strip() == pin['tree'],
          'temporary index differs from published tree')
    new_manifest = backup/'new-manifest.json'
    shutil.copy2(DST/MANIFEST, new_manifest)
    write_new(OUT/'activation-intent.json', dict(recorded_utc=utc(), base_commit=BASE, commit=head,
        private_backup=str(backup), index_before=index_before, coordination_before=current_prefix,
        preparation_coordination_prefix=prep['shared_before']['coordination'], helper_sha256=sha(Path(__file__))))
    phase = 'prepared'
    lock = index.with_name(index.name+'.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        check(git(SRC, 'symbolic-ref', 'HEAD') == BRANCH, 'shared branch switched')
        check_shared(prep)
        check(git(SRC, 'rev-parse', 'HEAD') == BASE and info(index) == index_before, 'shared HEAD/index moved')
        latest = (SRC/COORD).read_bytes()
        check_coord_prefix(current_prefix, latest)
        check(appendix not in latest, 'duplicate shared appendix')
        check((SRC/MANIFEST).read_bytes() == old_manifest, 'shared manifest moved')
        check(before == {name: info(SRC/name) for name in preserved}, 'preserved source changed')
        (backup/'coordination-at-lock.md').write_bytes(latest)
        latest_prefix = dict(bytes=len(latest), sha256=sha_bytes(latest))
        subprocess.run(['git', '-C', str(SRC), 'update-ref', BRANCH, head, BASE], check=True, env=ENV)
        phase = 'branch_updated'
        os.replace(temporary_index, index)
        phase = 'index_installed'
        os.replace(new_manifest, SRC/MANIFEST)
        phase = 'manifest_installed'
        before_append = (SRC/COORD).read_bytes()
        check_coord_prefix(latest_prefix, before_append)
        check(appendix not in before_append, 'duplicate concurrent appendix')
        append_fd = os.open(SRC/COORD, os.O_WRONLY | os.O_APPEND)
        try:
            check(os.write(append_fd, appendix) == len(appendix), 'partial coordination append')
        finally:
            os.close(append_fd)
        phase = 'coordination_appended'
    finally:
        check(os.fstat(fd).st_ino == lock.stat().st_ino, 'index lock replaced')
        os.close(fd)
        fd = None
        lock.unlink()
    check(git(SRC, 'symbolic-ref', 'HEAD') == BRANCH and git(SRC, 'rev-parse', 'HEAD') == head, 'activation HEAD differs')
    check(subprocess.run(['git', '-C', str(SRC), 'diff', '--cached', '--quiet'], env=ENV).returncode == 0,
          'new index differs from published HEAD')
    check(before == {name: info(SRC/name) for name in preserved}, 'activation changed preserved source')
    check((SRC/MANIFEST).read_bytes() == (DST/MANIFEST).read_bytes(), 'activated manifest differs')
    after_coord = (SRC/COORD).read_bytes()
    check(after_coord.startswith(before_append), 'pre-append coordination bytes changed')
    check(after_coord[len(before_append):].count(appendix) == 1, 'own appendix missing/duplicated')
    phase = 'postconditions_checked'
    recorded = utc()
    done = ('\n\n## '+recorded+' — Codex: DONE documentation snapshot activation\n\n'+
            prep['authorization']['activation_done_body'].replace('{commit}', head).rstrip()+'\n').encode()
    append_fd = os.open(SRC/COORD, os.O_WRONLY | os.O_APPEND)
    try:
        check(os.write(append_fd, done) == len(done), 'partial DONE append')
    finally:
        os.close(append_fd)
    phase = 'done_appended'
    final_coord = (SRC/COORD).read_bytes()
    check(final_coord.startswith(after_coord), 'post-activation coordination bytes changed')
    write_new(receipt_path, dict(recorded_utc=recorded, base_commit=BASE, commit=head,
        private_backup=str(backup), preserved_source_hashes=before, shared_index_matches_head=True,
        preparation_coordination_prefix=prep['shared_before']['coordination'], activation_coordination_prefix=current_prefix,
        at_lock_coordination_prefix=latest_prefix, coordination_prefixes_preserved=True,
        remote_verified=actual_remote_refs, scope=pin['scope'],
        shared_status=git(SRC, 'status', '--short', '--untracked-files=no'),
        source='Published exact SHA only; temporary index plus ref CAS; no reset, checkout, blanket add or unrelated-file rewrite.'))
    phase = 'success_receipt_written'
except BaseException as error:
    failure = dict(recorded_utc=utc(), last_completed_phase=phase, private_backup=str(backup) if backup else None,
                   base_commit=BASE, commit=head, error=repr(error), automatic_rollback=False)
    for label, args in [('head', ('rev-parse', 'HEAD')), ('branch', ('symbolic-ref', 'HEAD'))]:
        try:
            failure[label] = git(SRC, *args)
        except Exception as state_error:
            failure[label+'_read_error'] = repr(state_error)
    write_new(OUT/'activation-failure.json', failure)
    raise
print(json.dumps(dict(commit=head, preserved_paths=len(preserved), private_backup=str(backup))))
