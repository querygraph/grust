"""Copy only root-authorized, fully hashed frozen inputs into an isolated snapshot.

Not runnable from the draft template. No shared ref/index/prose writes.
"""
import argparse
import shutil
from common import *

parser = argparse.ArgumentParser()
parser.add_argument('--authorization', type=Path, required=True)
parser.add_argument('--authorization-sha256', required=True)
args = parser.parse_args()
check(sha(args.authorization) == args.authorization_sha256, 'authorization hash differs')
auth = load(args.authorization)
validate_authorization(auth)
check(not (OUT/'preparation.json').exists() and not (OUT/'frozen.json').exists(), 'already prepared')
detached(DST, BASE)
check(not git(DST, 'status', '--porcelain'), 'new worktree is not clean')
check(remote_refs() == dict.fromkeys(REFS, BASE), 'remote refs advanced; rebase preparation explicitly')
state = shared_state()
check(state['head'] == BASE and state['branch'] == BRANCH, 'shared branch moved')
check(subprocess.run(['git', '-C', str(SRC), 'diff', '--cached', '--quiet'], env=ENV).returncode == 0,
      'shared index contains staged edits')
selected = {}
for name, expected in auth['selected_sources'].items():
    path = selected_path(name)
    check(info(safe_path(SRC, str(path))) == expected, 'frozen source does not match authorization: '+name)
    check_selected_content(safe_path(SRC, str(path)), name)
    selected[name] = expected
for item in auth['required_json']:
    check(item['path'] in selected, 'closure receipt not selected')
    data = load(SRC/item['path'])
    for pointer, value in item['equals'].items():
        actual = data
        for key in pointer.split('.'):
            actual = actual[key]
        check(actual == value, 'closed-result guard failed: '+item['path']+' '+pointer)
check(REQUIRED_CLOSURES <= {x['path'] for x in auth['required_json']},
      'component, physical check and package closure receipts required')
prep = dict(recorded_utc=utc(), base_commit=BASE, selected_sources=selected, shared_before=state,
            authorization_sha256=args.authorization_sha256, authorization=auth,
            expected_remote_refs=dict.fromkeys(REFS, BASE))
original = load(DST/MANIFEST)
write_new(OUT/'base-manifest.json', original)
base_files = set(git(DST, 'ls-files').splitlines())
for name, expected in selected.items():
    target = safe_path(DST, name)
    if name in base_files and Path(name) not in MUTABLE_FILES:
        check(info(target) == expected, 'attempt to change immutable prior file: '+name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(safe_path(SRC, name), target)
    check(info(target) == expected, 'copied source differs: '+name)
base_coord = git_bytes(DST, 'show', BASE+':'+str(COORD))
check((DST/COORD).read_bytes() == base_coord, 'candidate coordination not pristine base')
appendix = ('\n\n## '+utc()+' — Codex: '+auth['coordination_title']+'\n\n'+auth['coordination_body'].rstrip()+'\n').encode()
(DST/COORD).write_bytes(base_coord+appendix)
for row in original['files']:
    path = Path(row['path'])
    if path not in MUTABLE_FILES | {COORD}:
        check(sha(DST/path) == row['sha256'], 'prior evidence changed: '+str(path))
paths = {Path(row['path']) for row in original['files']} | {Path(x) for x in selected} | {COORD}
manifest = dict(original)
manifest.update(recorded_utc=utc(), base_commit=BASE, scope=auth['scope'],
    publication_branches=[ref.removeprefix('refs/heads/') for ref in REFS],
    files=[dict(path=str(p), sha256=sha(DST/p), bytes=(DST/p).stat().st_size) for p in sorted(paths)],
    pending_excluded_subtrees=auth['excluded_scopes'],
    source_copy_guard='Only authorized exact source bytes/sizes/modes copied; shared coordination never copied. All prior evidence immutable except the two selected current root prose files and a candidate-only coordination append.',
    current_snapshot_cutoff=auth['cutoff'],
    archived_markdown_link_contexts=ARCHIVE_CONTEXTS)
# Historical cutoff fields remain evidence but cannot label this publication.
for key in ('frozen_observation_cutoff', 'observation_history_note'):
    manifest.pop(key, None)
(DST/MANIFEST).write_text(json.dumps(manifest, indent=2)+'\n')
prep['shared_after'] = check_shared(prep)
prep['manifest_sha256'] = sha(DST/MANIFEST)
prep['coordination_appendix'] = dict(bytes=len(appendix), sha256=sha_bytes(appendix))
write_new(OUT/'preparation.json', prep)
allowlist = sorted(set(selected) | {str(COORD), str(MANIFEST)})
subprocess.run(['git', '-C', str(DST), 'add', '--', *allowlist], check=True, env=ENV)
subprocess.run(['git', '-C', str(DST), 'diff', '--cached', '--check', '--', '*.md', '*.py', '*.rs', '*.toml'], check=True, env=ENV)
(OUT/'commit-message.txt').write_text(auth['commit_message'].rstrip()+'\n')
helpers = ['commit-message.txt', 'common.py', 'prepare_snapshot.py', 'guard.py', 'commit_and_gate.sh', 'publish.py', 'activate_shared.py']
pin = dict(recorded_utc=utc(), base=BASE, tree=git(DST, 'write-tree'),
    expected_remote_refs=dict.fromkeys(REFS, BASE), manifest_path=str(MANIFEST),
    manifest_sha256=sha(DST/MANIFEST), preparation_sha256=sha(OUT/'preparation.json'),
    base_manifest_sha256=sha(OUT/'base-manifest.json'), changed_paths=git(DST, 'diff', '--cached', '--name-only').splitlines(),
    source_allowlist=allowlist, helper_hashes={name:sha(OUT/name) for name in helpers},
    authorization_sha256=args.authorization_sha256, cutoff=auth['cutoff'], scope=auth['scope'],
    candidate_only_prose_differences=[])
check(set(pin['changed_paths']) <= set(allowlist), 'unexpected changed path')
write_new(OUT/'frozen.json', pin)
source_guard(pin, prep, 'candidate-before', BASE)
print(json.dumps(dict(tree=pin['tree'], manifest_sha256=pin['manifest_sha256'], files=len(paths))))
