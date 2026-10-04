"""Inspect, then remove only the completed 289/561 private host build caches.

The launcher requires both builds collected and all other containers stopped.
Inspection runs with /targets read-only; apply requires that preserved report.
Only literal target-host directories can be removed. Sources, exported binaries,
venv/wheels, receipts/logs and original ffcf build targets remain outside them.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

GIB = 1 << 30
BUILDS = (
    ('2894a962076d3cc404dd72ec736ebeb9239901f6', Path('/targets/sail-stream-2894a962076d')),
    ('56194b170155301ba91077f0ba3df31fe2c78b6b', Path('/targets/sail-compact-host-56194b170155')),
)
CACHES = tuple(root / 'target-host' for _, root in BUILDS)
OUTPUT = BUILDS[1][1] / 'host-cache-cleanup.json'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def snapshot(path):
    value, entries = hashlib.sha256(), 0
    for directory, folders, files in os.walk(path, followlinks=False):
        folders.sort()
        for name in sorted(folders + files):
            entry = Path(directory) / name
            info = entry.lstat()
            value.update(json.dumps([str(entry.relative_to(path)), info.st_mode, info.st_size,
                                     info.st_mtime_ns, info.st_ctime_ns,
                                     os.readlink(entry) if entry.is_symlink() else None]).encode())
            entries += 1
    return dict(metadata_sha256=value.hexdigest(), entries=entries)


def guard_source(root, sha):
    source = root / 'source'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True,
                                       env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).strip()
    if source.is_symlink() or source.resolve(strict=True) != source:
        raise RuntimeError('source path is not the retained literal directory')
    if git('rev-parse', 'HEAD') != sha or git('status', '--porcelain'):
        raise RuntimeError('completed source moved or is dirty')
    if subprocess.run(['git', '-C', str(source), 'symbolic-ref', '-q', 'HEAD'],
                      capture_output=True).returncode != 1:
        raise RuntimeError('completed source is not detached')


def processes_referencing_caches():
    markers = [str(path).removeprefix('/targets') for path in CACHES]
    blockers, unreadable = [], 0
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        referenced = False
        for field in ('cmdline', 'maps'):
            try:
                value = (process / field).read_text(errors='replace')
                referenced |= any(marker in value for marker in markers)
            except (FileNotFoundError, ProcessLookupError):
                pass
            except PermissionError:
                unreadable += 1
        try:
            links = [process / 'cwd', process / 'exe', *list((process / 'fd').iterdir())]
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            unreadable += 1
            links = [process / 'cwd', process / 'exe']
        for link in links:
            try:
                referenced |= any(marker in os.readlink(link) for marker in markers)
            except (FileNotFoundError, ProcessLookupError, OSError):
                pass
        if referenced:
            blockers.append(int(process.name))
    if blockers:
        raise RuntimeError(f'private host caches referenced by process IDs {blockers}')
    return dict(no_references_found_in_readable_proc_entries=True,
                unreadable_cmdline_maps_or_fd_entries=unreadable,
                scope='readable cmdline/maps/cwd/exe/fd; supplementary to serial idle-VM orchestration')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence289', required=True, type=Path)
    parser.add_argument('--evidence561', required=True, type=Path)
    parser.add_argument('--inspection', type=Path)
    parser.add_argument('--inspection-sha256')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply != bool(args.inspection and args.inspection_sha256):
        parser.error('apply requires the preserved inspection and its SHA256')
    if OUTPUT.exists():
        raise RuntimeError('cleanup receipt exists; do not repeat a prior attempt')
    protected, receipts = {}, []
    for (sha, root), evidence in zip(BUILDS, (args.evidence289, args.evidence561)):
        if root.is_symlink() or root.resolve(strict=True) != root:
            raise RuntimeError('build path is not the literal retained directory')
        evidence = evidence.resolve(strict=True)
        if evidence.parent != Path('/work'):
            raise RuntimeError('evidence must be a collected directory directly under read-only /work')
        receipt_path = root / 'rebuild-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('source_sha') != sha or receipt.get('outcome') != 'passed'
                or receipt.get('seed_unchanged') is not True):
            raise RuntimeError('require exact passing builds and completed seed guards')
        collection = json.loads((evidence / 'collection.json').read_text())
        if collection.get('source_sha') != sha or collection.get('outcome') != 'passed':
            raise RuntimeError('collected evidence identifies a different build')
        for name, expected in collection['sha256'].items():
            if Path(name).name != name or digest(evidence / name) != expected:
                raise RuntimeError('collected artifact differs or has an unsafe path')
        if digest(receipt_path) != digest(evidence / 'rebuild-receipt.json'):
            raise RuntimeError('live receipt differs from durable evidence')
        protected[str(receipt_path)] = digest(receipt_path)
        for key in ('host', 'native_wheel'):
            artifact = receipt[key]
            path = Path(artifact['path'])
            if not any(path.is_relative_to(item[1]) for item in BUILDS):
                raise RuntimeError('retained artifact is outside the two builds')
            protected[str(path)] = artifact['sha256']
        protected.update(receipt.get('protected_artifacts', {}))
        guard_source(root, sha)
        receipts.append(receipt)
    compact = receipts[1]
    if (compact.get('native_source_sha') != BUILDS[0][0] or
            compact.get('native_identity', {}).get('exact_tree_and_blob_match') is not True):
        raise RuntimeError('compact native source identity proof is missing')
    for path, expected in protected.items():
        resolved = Path(path).resolve(strict=True)
        if any(resolved.is_relative_to(cache) for cache in CACHES) or digest(path) != expected:
            raise RuntimeError('protected artifact differs or lies inside a deletion target')
    venv = BUILDS[0][1] / 'venv'
    venv_before = snapshot(venv)
    if any(venv_before[key] != compact['seed_venv_before'][key] for key in venv_before):
        raise RuntimeError('retained venv metadata differs from passing compact guard')
    caches = {}
    for cache in CACHES:
        if cache.is_symlink() or not cache.is_dir() or cache.resolve() != cache:
            raise RuntimeError('refuse any other cache path or symlink')
        caches[str(cache)] = dict(snapshot(cache), allocated_bytes=int(subprocess.check_output(
            ['du', '-sk', str(cache)], text=True).split()[0]) * 1024)
    free = shutil.disk_usage('/targets').free
    projected, selected = free, []
    for cache in CACHES:
        if projected >= 40 * GIB:
            break
        selected.append(str(cache))
        projected += caches[str(cache)]['allocated_bytes']
    record = dict(started_utc=utc(), outcome='inspected', script_sha256=digest(__file__),
                  builds=[sha for sha, _ in BUILDS], cache_inventory=caches,
                  free_bytes_before=free, desired_free_bytes=40 * GIB,
                  eligible_paths=[str(path) for path in CACHES],
                  projected_selected_paths=selected, projected_free_bytes=projected,
                  protected_artifacts_sha256=protected, retained_venv_metadata=venv_before,
                  process_scan=processes_referencing_caches(),
                  scope='only task-owned completed host caches; original ffcf targets untouched')
    if not args.apply:
        print(json.dumps(record, indent=2))
        return 0
    inspection = args.inspection.resolve(strict=True)
    if not inspection.is_relative_to('/work') or digest(inspection) != args.inspection_sha256:
        raise RuntimeError('inspection path/hash differs')
    prior = json.loads(inspection.read_text())
    for key in ('script_sha256', 'builds', 'cache_inventory', 'eligible_paths',
                'protected_artifacts_sha256', 'retained_venv_metadata'):
        if record[key] != prior.get(key):
            raise RuntimeError('guard changed since inspection: ' + key)
    record.update(outcome='started', inspection_sha256=args.inspection_sha256,
                  inspected_projected_paths=prior['projected_selected_paths'],
                  removed_paths=[], deletion_observations=[])
    OUTPUT.write_text(json.dumps(record, indent=2) + '\n')
    # Both literal caches were inspected and authorized conditionally. Use
    # actual free space before each removal, not du's predicted reclamation.
    for cache in CACHES:
        actual_free = shutil.disk_usage('/targets').free
        if actual_free >= 40 * GIB:
            break
        path = str(cache)
        record['deletion_observations'].append(dict(path=path, utc=utc(), free_bytes=actual_free))
        OUTPUT.write_text(json.dumps(record, indent=2) + '\n')
        shutil.rmtree(path)
        record['removed_paths'].append(path)
        OUTPUT.write_text(json.dumps(record, indent=2) + '\n')
    for path, expected in protected.items():
        if digest(path) != expected:
            raise RuntimeError('retained artifact changed: ' + path)
    if snapshot(venv) != venv_before:
        raise RuntimeError('retained venv changed')
    for sha, root in BUILDS:
        guard_source(root, sha)
    free_after = shutil.disk_usage('/targets').free
    record.update(outcome='passed', finished_utc=utc(), free_bytes_after=free_after,
                  removed_caches_absent=all(not Path(path).exists() for path in record['removed_paths']),
                  free_space_goal_met=free_after >= 40 * GIB,
                  retained_artifact_hashes_unchanged=True, retained_venv_metadata_unchanged=True)
    OUTPUT.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
