from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
import tomllib

root = Path('/Users/alexy/src/sail-sdp-gate')
candidate = json.loads(Path('/tmp/sail-sdp-orc-precision-vendor-candidate.json').read_text())
orc = Path('/Users/alexy/src/orc-rust-sdp-gate')
pin = '579c04b3aedefc007f09371894f01c90ef9e75c2'


def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


assert git('rev-parse', 'HEAD') == candidate['commit']
assert not git('status', '--porcelain')
assert subprocess.run(['git', '-C', str(root), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
# Preserve the packaged upstream README byte-for-byte, including its existing
# trailing blank line. Its exact bytes are checked against the package below.
# Whitespace checks still cover all authored files and every vendored Rust file.
subprocess.run(['git', '-C', str(root), 'diff', '--check', candidate['base'], candidate['commit'], '--', '.', ':!vendor/orc-rust/README.md'], check=True)
subprocess.run(['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python', 'scripts/spark-pipelines-tests/verify_vendor.py'], cwd=root, check=True)
manifest = json.loads((root / 'vendor/orc-rust/SOURCE.json').read_text())
assert manifest['commit'] == pin and len(manifest['patches']) == 7
actual_files = {str(p.relative_to(root / 'vendor/orc-rust')) for p in (root / 'vendor/orc-rust').rglob('*') if p.is_file()}
assert actual_files == set(manifest['files_sha256']) | {'SOURCE.json'}
archive_path = orc / 'target/package/orc-rust-0.9.0.crate'
assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == manifest['package']['sha256']
with tarfile.open(archive_path) as archive:
    for member in archive.getmembers():
        relative = Path(member.name).relative_to('orc-rust-0.9.0')
        if str(relative) == 'Cargo.lock':
            continue
        assert (root / 'vendor/orc-rust' / relative).read_bytes() == archive.extractfile(member).read()
        if str(relative).startswith('src/'):
            source = subprocess.check_output(['git', '-C', str(orc), 'show', pin + ':' + str(relative)])
            assert source == (root / 'vendor/orc-rust' / relative).read_bytes()
license_bytes = subprocess.check_output(['git', '-C', str(orc), 'show', pin + ':LICENSE'])
assert (root / 'vendor/orc-rust/LICENSE').read_bytes() == license_bytes
workspace = tomllib.loads((root / 'Cargo.toml').read_text())
assert 'vendor/orc-rust' in workspace['workspace']['exclude']
assert workspace['workspace']['dependencies']['orc-rust'] == {'path': 'vendor/orc-rust', 'default-features': False, 'features': ['async']}
metadata = subprocess.check_output(['cargo', '+1.98.1', 'metadata', '--no-deps', '--locked', '--offline', '--format-version', '1'], cwd=root, text=True)
Path('/tmp/sail-sdp-orc-vendor-metadata.json').write_text(metadata)
assert not any(package['name'] == 'orc-rust' for package in json.loads(metadata)['packages'])
subprocess.run(['cargo', '+1.98.1', 'metadata', '--manifest-path', 'vendor/orc-rust/Cargo.toml', '--no-deps', '--offline', '--format-version', '1'], cwd=root, stdout=subprocess.DEVNULL, check=True)
assert not git('diff', candidate['base'], candidate['commit'], '--', 'Cargo.lock')
assert git('rev-parse', 'HEAD') == candidate['commit']
assert not git('status', '--porcelain')
print('PASS portable ORC snapshot: exact gated source/package, seven patch revisions, license, hashes, excluded workspace membership and unchanged runtime lock; ' + candidate['commit'])
