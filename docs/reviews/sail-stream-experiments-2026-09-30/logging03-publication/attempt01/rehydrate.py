"""Restore the exact raw collection into a new directory, without remote access."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def relative(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or str(p) != name or '\\' in name:
        raise ValueError('noncanonical relative path')
    return p


def checked(root, name):
    p = root.joinpath(*relative(name).parts)
    if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents if x != root.parent):
        raise ValueError('missing, symlink or non-file input')
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('input escapes package')
    return p


def archive_members(path):
    members = {}
    with tarfile.open(path, 'r:') as archive:
        for entry in archive:
            name = relative(entry.name)
            if len(name.parts) != 1 or not entry.isfile() or entry.name in members:
                raise ValueError('archive must contain unique flat regular files')
            digest = hashlib.sha256()
            count = 0
            with archive.extractfile(entry) as stream:
                for block in iter(lambda: stream.read(1 << 20), b''):
                    count += len(block)
                    digest.update(block)
            if count != entry.size:
                raise ValueError('archive member size mismatch')
            members[entry.name] = {'bytes': count, 'sha256': digest.hexdigest()}
    return members


def restore(package, destination):
    package = package.resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError('destination must not exist')
    destination = destination.absolute()
    if destination.resolve().is_relative_to(package) or package.is_relative_to(destination.resolve()):
        raise ValueError('destination and package must be disjoint')
    manifest = json.loads(checked(package, 'manifest.json').read_text())
    if manifest['schema'] != 'logging03-lossless-package-v1':
        raise ValueError('unsupported manifest')
    if fingerprint(Path(__file__)) != manifest['rehydration_helper']:
        raise ValueError('rehydration helper differs')
    for name, pin in manifest['package_files'].items():
        if fingerprint(checked(package, name)) != pin:
            raise ValueError('package file hash mismatch: ' + name)
    required = sum(p['bytes'] for p in manifest['raw_tree'].values()) + (256 << 20)
    if shutil.disk_usage(destination.parent).free < required:
        raise ValueError('insufficient destination disk admission')
    destination.mkdir()
    raw_tar = destination / 'diagnostics.tar'
    archive_pin = manifest['raw_tree']['diagnostics.tar']
    count = 0
    with gzip.open(checked(package, 'diagnostics.tar.gz'), 'rb') as source, raw_tar.open('xb') as target:
        while block := source.read(1 << 20):
            count += len(block)
            if count > archive_pin['bytes']:
                raise ValueError('decompressed archive exceeds pinned size')
            target.write(block)
    if fingerprint(raw_tar) != archive_pin:
        raise ValueError('original archive hash differs')
    if archive_members(raw_tar) != manifest['archive_members']:
        raise ValueError('archive member inventory differs')
    diagnostics = destination / 'diagnostics'
    diagnostics.mkdir()
    with tarfile.open(raw_tar, 'r:') as archive:
        for entry in archive:
            with archive.extractfile(entry) as source, (diagnostics / entry.name).open('xb') as target:
                shutil.copyfileobj(source, target, 1 << 20)
    for name, pin in manifest['raw_tree'].items():
        relative(name)
        if name == 'diagnostics.tar' or name.startswith('diagnostics/'):
            continue
        source = checked(package, 'metadata/' + name)
        if fingerprint(source) != pin:
            raise ValueError('metadata differs')
        target = destination.joinpath(*relative(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as reader, target.open('xb') as writer:
            shutil.copyfileobj(reader, writer, 1 << 20)
    actual = {str(p.relative_to(destination)): fingerprint(p) for p in destination.rglob('*') if p.is_file()}
    if actual != manifest['raw_tree']:
        raise ValueError('restored tree differs')
    for name, pin in manifest['package_files'].items():
        if fingerprint(checked(package, name)) != pin:
            raise ValueError('package changed during restoration')
    return {'outcome': 'EXACT_RAW_COLLECTION_RESTORED', 'files': actual,
            'manifest': fingerprint(package / 'manifest.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    receipt = args.receipt.absolute()
    if receipt.exists() or receipt.is_symlink() or receipt.resolve().is_relative_to(output.resolve()) or receipt.resolve().is_relative_to(args.package.resolve()):
        parser.error('receipt must be new and outside output/package')
    report = {'started_utc': datetime.now(timezone.utc).isoformat()}
    try:
        report.update(restore(args.package, output))
    except Exception as error:
        report.update(outcome='RESTORATION_FAILED', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with receipt.open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')


if __name__ == '__main__':
    main()
