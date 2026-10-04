"""Shared primitives for the reviewed documentation-only publication workflow."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

SRC = Path('/Users/alexy/src/grust')
DST = Path('/private/tmp/grust-sail-review-ownership-docs-v2')
OUT = Path('/private/tmp/grust-sail-review-ownership-publication-v2')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '980da04151cd5860017a06580a658bdf7e133c40'
ORIGIN = 'git@github.com:querygraph/grust.git'
REFS = ['refs/heads/work/proposal-v5', 'refs/heads/work/sail-graph-review']
BRANCH = REFS[0]
MANIFEST = REL/'DOCUMENTATION-SNAPSHOT.json'
COORD = Path('codex-to-codex.md')
MUTABLE_PROSE = {REL/'RESULTS.md'}
MUTABLE_FILES = MUTABLE_PROSE | {REL/'verify_documentation_snapshot.py'}
REVIEW_INPUTS = {Path('docs/SEM-REVIEW-2.md'), Path('docs/STREAM-LOSS-STATUS.md')}
ALLOWED_DIRS = {
    'argentea-rank-wcc-input-lifetime', 'argentea-cursor-lease-control',
    'documentation-validation-publication',
    'physical-output-execution-preparation', 'documentation-archive-context',
}
ALLOWED_FILES = {
    'RESULTS.md', 'verify_documentation_snapshot.py', 'documentation-validation-activation.json',
    'argentea-rank-wcc-input-lifetime-delivery.json',
}
REQUIRED_CLOSURES = {
    str(REL/'argentea-rank-wcc-input-lifetime/final-receipt.json'),
    str(REL/'argentea-rank-wcc-input-lifetime/extended-exact-gate/receipt.json'),
    str(REL/'argentea-rank-wcc-input-lifetime-delivery.json'),
}
# Expanded component closure only; the earlier a41 gate remains historical evidence.
COMPONENT_COMMIT = '33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9'
COMPONENT_TREE = '3f4399056199b49708340abf0b4d1205fca860dd'
COMPONENT_FINAL = str(REL/'argentea-rank-wcc-input-lifetime/final-receipt.json')
COMPONENT_EXACT = str(REL/'argentea-rank-wcc-input-lifetime/extended-exact-gate/receipt.json')
COMPONENT_DELIVERY = str(REL/'argentea-rank-wcc-input-lifetime-delivery.json')
CLOSED_PINS = {
    COMPONENT_FINAL: 'eff934be8adb0d9aa867596148b9fd9586fed96f1ba55ab74b2be35c9fa95380',
    COMPONENT_EXACT: 'a5d00a6905fd8c1336945ff76941804f317bb4ee0e9d4caeec9ca604e202798e',
}
CLOSURE_PREDICATES = {
    COMPONENT_FINAL: {'outcome': 'EXACT_COMPONENT_GATE_PASS', 'commit': COMPONENT_COMMIT,
                      'tree': COMPONENT_TREE, 'exact_gate': 'extended-exact-gate/receipt.json',
                      'exact_gate_receipt_sha256': CLOSED_PINS[COMPONENT_EXACT]},
    COMPONENT_EXACT: {'outcome': 'PASS', 'head': COMPONENT_COMMIT,
                      'tree': COMPONENT_TREE, 'exact': True},
    COMPONENT_DELIVERY: {'outcome': 'PUSHED_AND_REMOTELY_VERIFIED',
                         'commit': COMPONENT_COMMIT, 'tree': COMPONENT_TREE},
}
ARCHIVE_CONTEXTS = {'docs/reviews/sail-stream-experiments-2026-09-30/documentation-validation-publication/preparation-attempt01/RESULTS.md': {'original_path': 'docs/reviews/sail-stream-experiments-2026-09-30/RESULTS.md', 'source_manifest': 'docs/reviews/sail-stream-experiments-2026-09-30/documentation-validation-publication/preparation-attempt01/DOCUMENTATION-SNAPSHOT.json'}}
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')


def utc():
    return datetime.now(timezone.utc).isoformat()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], env=ENV).decode().strip()


def git_bytes(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], env=ENV)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def info(path):
    check(path.is_file() and not path.is_symlink(), 'not a regular file: '+str(path))
    data = path.read_bytes()
    return dict(sha256=sha_bytes(data), bytes=len(data), mode=oct(path.stat().st_mode & 0o777))


def sha(path):
    return info(path)['sha256']


def load(path):
    return json.loads(path.read_text())


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def relative(name):
    path = PurePosixPath(name)
    check(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts,
          'unsafe relative path: '+name)
    check(path.as_posix() == name, 'noncanonical relative path: '+name)
    return Path(name)


def selected_path(name):
    path = relative(name)
    check(path.is_relative_to(REL), 'source outside review folder: '+name)
    local = path.relative_to(REL)
    check(str(local) in ALLOWED_FILES or local.parts[0] in ALLOWED_DIRS,
          'source outside fixed preparation scope: '+name)
    check('__pycache__' not in path.parts and path.suffix != '.pyc', 'cache selected')
    check(path.suffix.lower() not in ('.parquet', '.bin', '.so', '.dylib', '.exe', '.whl', '.tar', '.gz', '.zip'),
          'private/binary data selected: '+name)
    return path


def safe_path(root, name):
    path = relative(name)
    current = root
    for part in path.parts:
        current = current/part
        check(not current.is_symlink(), 'symlink in selected path: '+str(current))
    return current


def check_origin(root):
    for options in (('--all',), ('--push', '--all')):
        check(git(root, 'remote', 'get-url', *options, 'origin').splitlines() == [ORIGIN],
              'origin destination changed')
    return ORIGIN


def validate_authorization(auth):
    check(isinstance(auth, dict), 'authorization must be an object')
    check(auth.get('archived_markdown_link_contexts') == ARCHIVE_CONTEXTS,
          'reviewed archive link context differs')
    check(auth.get('status') == 'AUTHORIZED_FROZEN_INPUTS' and auth.get('base') == BASE,
          'inputs not authorized')
    for key in ('scope', 'coordination_title', 'coordination_body', 'commit_message',
                'activation_done_body', 'cutoff'):
        check(isinstance(auth.get(key), str) and auth[key].strip(), 'missing reviewed prose: '+key)
    check(isinstance(auth.get('excluded_scopes'), list) and auth['excluded_scopes']
          and all(isinstance(x, str) and x.strip() for x in auth['excluded_scopes']), 'missing exclusions')
    check(isinstance(auth.get('selected_sources'), dict) and auth['selected_sources'], 'missing frozen sources')
    for name, expected in auth['selected_sources'].items():
        selected_path(name)
        check(isinstance(expected, dict) and set(expected) == {'sha256', 'bytes', 'mode'}, 'invalid source pin')
        check(isinstance(expected['sha256'], str) and len(expected['sha256']) == 64
              and all(c in '0123456789abcdef' for c in expected['sha256']), 'invalid source hash')
        check(type(expected['bytes']) is int and expected['bytes'] >= 0, 'invalid source size')
        check(expected['mode'] in ('0o644', '0o755'), 'unexpected source mode')
    check(isinstance(auth.get('required_json'), list) and auth['required_json'], 'missing closure guards')
    for item in auth['required_json']:
        check(isinstance(item, dict) and item.get('path') in auth['selected_sources'], 'closure receipt not selected')
        check(isinstance(item.get('equals'), dict) and item['equals']
              and all(isinstance(k, str) and k and all(k.split('.')) for k in item['equals']), 'invalid closure guard')
    check(REQUIRED_CLOSURES <= {x['path'] for x in auth['required_json']},
          'new component final/exact gate and outer delivery closure receipts required')
    for path, predicates in CLOSURE_PREDICATES.items():
        matches = [item['equals'] for item in auth['required_json'] if item['path'] == path]
        check(len(matches) == 1 and all(matches[0].get(k) == v for k, v in predicates.items()),
              'expanded component closure predicates differ: '+path)
    for path, digest in CLOSED_PINS.items():
        check(auth['selected_sources'][path]['sha256'] == digest,
              'expanded component closed receipt hash differs: '+path)


def index_path():
    return Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))


def shared_state():
    return dict(origin=check_origin(SRC), head=git(SRC, 'rev-parse', 'HEAD'), branch=git(SRC, 'symbolic-ref', 'HEAD'),
                index=info(index_path()), coordination=info(SRC/COORD),
                prose={str(path): info(SRC/path) for path in MUTABLE_PROSE},
                review_inputs={str(path): info(SRC/path) for path in REVIEW_INPUTS})


def check_coord_prefix(expected, current):
    check(len(current) >= expected['bytes'], 'coordination truncated')
    check(sha_bytes(current[:expected['bytes']]) == expected['sha256'], 'coordination prefix edited')


def check_shared(preparation):
    """Allow new shared coordination suffix bytes only; never import that suffix."""
    before = preparation['shared_before']
    now = shared_state()
    for key in ('origin', 'head', 'branch', 'index', 'prose', 'review_inputs'):
        check(now[key] == before[key], 'shared '+key+' changed')
    check(now['coordination']['mode'] == before['coordination']['mode'], 'coordination mode changed')
    current = (SRC/COORD).read_bytes()
    check_coord_prefix(before['coordination'], current)
    for name, expected in preparation['selected_sources'].items():
        check(info(safe_path(SRC, name)) == expected, 'selected source changed: '+name)
    return dict(now=now, captured_coordination_prefix=before['coordination'],
                appended_coordination_bytes=len(current)-before['coordination']['bytes'])


def detached(root, expected):
    check(git(root, 'rev-parse', 'HEAD') == expected, 'unexpected detached HEAD')
    check(subprocess.run(['git', '-C', str(root), 'symbolic-ref', '-q', 'HEAD'],
                         env=ENV, capture_output=True).returncode == 1, 'attached candidate')


def remote_refs():
    check_origin(DST)
    rows = git(DST, 'ls-remote', 'origin', *REFS).splitlines()
    result = {line.split()[1]: line.split()[0] for line in rows}
    check(set(result) == set(REFS) and len(rows) == len(REFS), 'unexpected remote ref inventory')
    return result


def source_guard(pin, preparation, phase, head):
    check_shared(preparation)
    detached(DST, head)
    check_origin(DST)
    check(git(DST, 'write-tree') == pin['tree'], 'candidate index tree changed')
    check(subprocess.run(['git', '-C', str(DST), 'diff', '--quiet'], env=ENV).returncode == 0,
          'unstaged candidate changes')
    check(not git(DST, 'ls-files', '--others', '--exclude-standard'), 'untracked candidate files')
    check(sha(DST/MANIFEST) == pin['manifest_sha256'], 'manifest changed')
    if phase.startswith('exact'):
        check(not git(DST, 'status', '--porcelain'), 'exact candidate not clean')
        check(git(DST, 'rev-parse', 'HEAD^') == BASE and git(DST, 'rev-parse', 'HEAD^{tree}') == pin['tree'],
              'exact candidate not direct matching child')
    for name, expected in preparation['selected_sources'].items():
        check(info(safe_path(DST, name)) == expected, 'candidate selected bytes/mode changed: '+name)
    original = load(OUT/'base-manifest.json')
    for row in original['files']:
        path = Path(row['path'])
        if path not in MUTABLE_FILES | {COORD}:
            check(sha(DST/path) == row['sha256'], 'prior evidence changed: '+str(path))
    changed = git(DST, 'diff', '--name-only', BASE).splitlines()
    check(set(changed) == set(pin['changed_paths']), 'candidate changed path inventory differs')
    for name, expected in pin['helper_hashes'].items():
        check(sha(OUT/name) == expected, 'publication helper changed: '+name)
