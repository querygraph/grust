"""Install and byte-verify the already packaged, qualified native ORC revision."""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import json
import subprocess
import tarfile
import tempfile

SAIL = Path('/Users/alexy/src/sail-pipelines-proposal')
NATIVE = Path('/Users/alexy/src/orc-rust-sdp-gate')
PIN = '0653cb2287e6bdb8352aeafbaa816ff25da72f76'
PREVIOUS = '579c04b3aedefc007f09371894f01c90ef9e75c2'
ARCHIVE = Path('/tmp/sail-sdp-orc-timezone-package-0653cb2/package/orc-rust-0.9.0.crate')
VENDOR = SAIL / 'vendor/orc-rust'
PROOF = Path('/tmp/sail-sdp-orc-timezone-vendor-install.json')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])

def digest(data):
    return hashlib.sha256(data).hexdigest()

def native_clean():
    assert git(NATIVE, 'rev-parse', 'HEAD').decode().strip() == PIN
    assert not git(NATIVE, 'status', '--porcelain')
    assert subprocess.run(['git', '-C', str(NATIVE), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1

native_clean()
assert not git(SAIL, 'status', '--porcelain', '--', 'vendor/orc-rust')
lock_before = (SAIL / 'Cargo.lock').read_bytes()
old = json.loads((VENDOR / 'SOURCE.json').read_text())
assert old['commit'] == PREVIOUS
old_paths = {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob('*') if p.is_file()}
assert old_paths == set(old['files_sha256']) | {'SOURCE.json'}
for name, expected in old['files_sha256'].items():
    assert digest((VENDOR / name).read_bytes()) == expected, name
patches = [dict(zip(('commit', 'subject'), line.split('\t', 1)))
           for line in git(NATIVE, 'log', '--reverse', '--format=%H%x09%s', old['upstream_commit'] + '..' + PIN).decode().splitlines()]
assert patches[:len(old['patches'])] == old['patches']
assert len(patches) == 9 and patches[-1]['commit'] == PIN
archive_hash = digest(ARCHIVE.read_bytes())
with tempfile.TemporaryDirectory(prefix='sail-orc-timezone-package-', dir='/tmp') as directory:
    stage = Path(directory)
    members = {}
    excluded = []
    with tarfile.open(ARCHIVE) as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            assert path.parts[0] == 'orc-rust-0.9.0' and '..' not in path.parts
            assert member.isfile(), member.name
            relative = path.relative_to('orc-rust-0.9.0').as_posix()
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            if relative == 'Cargo.lock':
                excluded.append({'path': relative, 'bytes': len(data), 'sha256': digest(data)})
                continue
            assert relative not in members
            members[relative] = data
            if relative.startswith('src/') or relative == 'README.md':
                assert data == git(NATIVE, 'show', PIN + ':' + relative), relative
            if relative == 'Cargo.toml.orig':
                assert data == git(NATIVE, 'show', PIN + ':Cargo.toml')
    assert [x['path'] for x in excluded] == ['Cargo.lock']
    vcs = json.loads(members['.cargo_vcs_info.json'])
    assert vcs['git']['sha1'] == PIN and not vcs['git'].get('dirty', False)
    assert 'LICENSE' not in members
    members['LICENSE'] = git(NATIVE, 'show', PIN + ':LICENSE')
    manifest = {**old, 'commit': PIN, 'patches': patches,
                'package': {**old['package'], 'command': 'cargo +1.98.1 package --locked --no-verify',
                            'sha256': archive_hash},
                'files_sha256': {name: digest(data) for name, data in sorted(members.items())}}
    for name, data in members.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (stage / 'SOURCE.json').write_text(json.dumps(manifest, indent=2) + '\n')
    new_paths = set(members) | {'SOURCE.json'}
    changed = sorted(name for name in old_paths | new_paths
                     if name not in old_paths or name not in new_paths
                     or (VENDOR / name).read_bytes() != (stage / name).read_bytes())
    native_clean()
    for name in sorted(old_paths - new_paths):
        (VENDOR / name).unlink()
    for name in sorted(new_paths):
        destination = VENDOR / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((stage / name).read_bytes())

assert not (VENDOR / 'Cargo.lock').exists()
assert (SAIL / 'Cargo.lock').read_bytes() == lock_before
assert {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob('*') if p.is_file()} == new_paths
for name, expected in manifest['files_sha256'].items():
    assert digest((VENDOR / name).read_bytes()) == expected
native_clean()
proof = {'recorded_at': datetime.now(timezone.utc).isoformat(),
         'native_commit': PIN, 'previous_native_commit': PREVIOUS,
         'native_checkout': str(NATIVE), 'native_clean_detached_before_and_after': True,
         'cargo_command': 'cargo +1.98.1 package --locked --no-verify',
         'cargo_target_dir': '/tmp/sail-sdp-orc-timezone-package-0653cb2',
         'archive': str(ARCHIVE), 'archive_sha256': archive_hash,
         'excluded_package_files': excluded, 'added_from_git': ['LICENSE'],
         'patch_count': len(patches), 'vendor_files_excluding_SOURCE': len(members),
         'changed_files': changed, 'changed_file_count': len(changed),
         'sail_Cargo_lock_sha256_unchanged': digest(lock_before),
         'verification': 'Installed bytes match exact package; packaged Rust, README and original manifest match pinned Git; LICENSE from same commit; all SOURCE hashes match.',
         'runtime_qualification': 'No builds or runtime tests in this packaging/install step.'}
PROOF.write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof, indent=2))
