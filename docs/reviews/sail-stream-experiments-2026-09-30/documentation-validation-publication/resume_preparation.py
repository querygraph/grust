"""Finish the exact partially staged snapshot after the raw-evidence check failed.

No recopy, reappend, evidence normalization or reset. The existing documentation
gate applies whitespace rules to authored md/py/rs/toml; keep that same scope.
"""
from common import *

check(not (OUT/'frozen.json').exists(), 'snapshot already frozen')
prep = load(OUT/'preparation.json')
failure = load(OUT/'preparation-attempt01-failure.json')
refresh = load(OUT/'preparation-refresh.json')
auth = load(OUT/'authorized-inputs.json')
validate_authorization(auth)
check(prep['authorization'] == auth and prep['authorization_sha256'] == sha(OUT/'authorized-inputs.json'),
      'original authorization changed')
check(prep['selected_sources'] == auth['selected_sources'], 'original selected source set changed')
check(failure['outcome'] == 'PREPARATION_FAILED_BEFORE_GATE_OR_COMMIT', 'unexpected predecessor')
detached(DST, BASE)
check_shared(prep)
check(remote_refs() == dict.fromkeys(REFS, BASE), 'remote refs moved')
check(refresh['outcome'] == 'REVIEWED_PROSE_PRECISION_REFRESH_BEFORE_FREEZE', 'unexpected refresh')
check(refresh['retained_failure_sha256'] == sha(OUT/'preparation-attempt01-failure.json') and
      refresh['previous_failed_tree'] == failure['index_tree'], 'failed predecessor changed')
check(refresh['authorization_sha256'] == sha(OUT/'authorized-inputs.json'), 'refresh authorization changed')
check(set(git(DST, 'diff', '--name-only', failure['index_tree'], refresh['index_tree']).splitlines()) ==
      {str(REL/'RESULTS.md'), str(MANIFEST)}, 'refresh changed other evidence')
check(git(DST, 'write-tree') == refresh['index_tree'], 'partially staged tree changed')
check(sha(DST/MANIFEST) == prep['manifest_sha256'] == refresh['manifest_sha256'], 'manifest changed')
check(not git(DST, 'ls-files', '--others', '--exclude-standard'), 'untracked candidate files')
subprocess.run(['git', '-C', str(DST), 'diff', '--quiet'], check=True, env=ENV)
for name, expected in prep['selected_sources'].items():
    check(info(safe_path(DST, name)) == expected, 'candidate source changed: '+name)
original = load(OUT/'base-manifest.json')
for row in original['files']:
    path = Path(row['path'])
    if path not in MUTABLE_PROSE | {COORD}:
        check(sha(DST/path) == row['sha256'], 'prior evidence changed: '+str(path))
base_coord = git_bytes(DST, 'show', BASE+':'+str(COORD))
coord = (DST/COORD).read_bytes()
check(coord.startswith(base_coord), 'candidate coordination prefix changed')
appendix = coord[len(base_coord):]
check(dict(bytes=len(appendix), sha256=sha_bytes(appendix)) == prep['coordination_appendix'],
      'candidate appendix changed')
allowlist = sorted(set(prep['selected_sources']) | {str(COORD), str(MANIFEST)})
changed = git(DST, 'diff', '--cached', '--name-only').splitlines()
check(set(changed) <= set(allowlist), 'unexpected staged paths')
command = ['git', '-C', str(DST), 'diff', '--cached', '--check', '--',
           '*.md', '*.py', '*.rs', '*.toml']
result = subprocess.run(command, env=ENV, capture_output=True)
(OUT/'preparation-authored-whitespace.log').write_bytes(result.stdout+result.stderr)
result.check_returncode()
with (OUT/'commit-message.txt').open('x') as stream:
    stream.write(auth['commit_message'].rstrip()+'\n')
helpers = ['commit-message.txt', 'common.py', 'prepare_snapshot.py', 'resume_preparation.py',
           'guard.py', 'commit_and_gate.sh', 'publish.py', 'activate_shared.py']
pin = dict(recorded_utc=utc(), base=BASE, tree=refresh['index_tree'],
    expected_remote_refs=dict.fromkeys(REFS, BASE), manifest_path=str(MANIFEST),
    manifest_sha256=sha(DST/MANIFEST), preparation_sha256=sha(OUT/'preparation.json'),
    base_manifest_sha256=sha(OUT/'base-manifest.json'), changed_paths=changed,
    source_allowlist=allowlist, helper_hashes={name:sha(OUT/name) for name in helpers},
    authorization_sha256=sha(OUT/'authorized-inputs.json'), cutoff=auth['cutoff'], scope=auth['scope'],
    candidate_only_prose_differences=[], retained_preparation_failure_sha256=sha(OUT/'preparation-attempt01-failure.json'),
    precision_refresh_sha256=sha(OUT/'preparation-refresh.json'),
    whitespace_scope='Matches existing documentation verifier: authored md/py/rs/toml; immutable raw logs/patches remain byte-exact.')
write_new(OUT/'frozen.json', pin)
source_guard(pin, prep, 'candidate-before', BASE)
write_new(OUT/'preparation-resume.json', dict(recorded_utc=utc(), outcome='PREPARATION_RESUMED_WITHOUT_SOURCE_CHANGE',
    original_failed_tree=failure['index_tree'], frozen_tree=pin['tree'], frozen_sha256=sha(OUT/'frozen.json'),
    command=command, returncode=result.returncode, scope=pin['whitespace_scope']))
print(json.dumps(dict(tree=pin['tree'], manifest_sha256=pin['manifest_sha256'], changed_paths=len(changed))))
