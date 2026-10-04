"""Remove only the completed 289 build's private native cache after collection.

Run in a short container sharing the VM PID namespace, the targets volume, and
the read-only evidence bind. The caller first requires no running containers.
Source, wheels, venv, host binary, logs, and original ffcf targets are retained.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

SEED_SHA = '2894a962076d3cc404dd72ec736ebeb9239901f6'
RUN = Path('/targets/sail-stream-2894a962076d')
CACHE = RUN / 'target-native'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve(strict=True)
    if not evidence.is_relative_to('/work'):
        parser.error('evidence must be the read-only collected build directory')
    receipt_path = RUN / 'rebuild-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if (receipt['source_sha'] != SEED_SHA or receipt['outcome'] != 'passed'
            or receipt.get('seed_unchanged') is not True):
        raise RuntimeError('require the completed passing 289 build')
    collection = json.loads((evidence / 'collection.json').read_text())
    if collection['source_sha'] != SEED_SHA or collection['outcome'] != 'passed':
        raise RuntimeError('collected evidence identifies a different build')
    for name, expected in collection['sha256'].items():
        if digest(evidence / name) != expected:
            raise RuntimeError(f'collected artifact differs: {name}')
    if digest(receipt_path) != digest(evidence / 'rebuild-receipt.json'):
        raise RuntimeError('current build receipt differs from collected evidence')
    if (RUN.is_symlink() or CACHE.is_symlink() or not CACHE.is_dir()
            or CACHE.resolve() != Path('/targets/sail-stream-2894a962076d/target-native')):
        raise RuntimeError('refuse any other cache path or symlink')
    protected = {receipt_path: digest(receipt_path)}
    for key in ('host', 'native_wheel'):
        artifact = receipt[key]
        path = Path(artifact['path'])
        if not path.is_relative_to(RUN) or digest(path) != artifact['sha256']:
            raise RuntimeError(f'build artifact mismatch: {key}')
        protected[path] = artifact['sha256']
    test_binaries = {}
    for name in ('nutmeg-core-tests', 'argentea-core-tests', 'native-adapter-tests'):
        log = (evidence / (name + '.log')).read_text()
        paths = [Path(value) for value in re.findall(r'Running .*?\(([^)]+)\)', log)]
        if not paths:
            raise RuntimeError(f'no executed test binary found in {name}')
        for path in paths:
            # Cargo renders target paths relative to its /targets working directory.
            if not path.is_absolute():
                path = Path('/targets') / path
            if not path.resolve(strict=True).is_relative_to(CACHE):
                raise RuntimeError('test binary is not inside private cache')
            test_binaries[str(path)] = digest(path)
    # Inspect visible VM processes, not only the cleanup container. This scan
    # is supplementary to the caller's serial, idle-VM orchestration: inaccessible
    # proc entries and maps-only references are not covered. Do not print argv.
    marker = '/sail-stream-2894a962076d/target-native'
    blockers = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            referenced = marker in (process / 'cmdline').read_bytes().decode(errors='replace')
            for link in [process / 'cwd', process / 'exe', *list((process / 'fd').iterdir())]:
                try:
                    referenced |= marker in os.readlink(link)
                except (FileNotFoundError, PermissionError, OSError):
                    pass
            if referenced:
                blockers.append(int(process.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    if blockers:
        raise RuntimeError(f'private native cache is still referenced by process IDs {blockers}')
    output = RUN / 'native-cache-cleanup.json'
    if output.exists():
        raise RuntimeError('cleanup receipt already exists; no repeat removal')
    size = int(subprocess.check_output(['du', '-sk', str(CACHE)], text=True).split()[0]) * 1024
    free_before = shutil.disk_usage('/targets').free
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='started',
                  removed_path=str(CACHE), allocated_bytes_before=size,
                  script_sha256=digest(__file__), evidence=str(evidence),
                  no_references_found_in_readable_proc_entries=True,
                  proc_scan_scope='readable cmdline/cwd/exe/fd; maps-only references excluded; requires serial idle VM',
                  executed_test_binaries_sha256=test_binaries,
                  retained_artifacts_sha256={str(k): v for k, v in protected.items()},
                  free_bytes_before=free_before)
    output.write_text(json.dumps(record, indent=2) + '\n')
    shutil.rmtree(CACHE)
    for path, expected in protected.items():
        if digest(path) != expected:
            raise RuntimeError(f'retained artifact changed: {path}')
    record.update(outcome='passed', finished_utc=datetime.now(timezone.utc).isoformat(),
                  cache_absent=not CACHE.exists(), free_bytes_after=shutil.disk_usage('/targets').free)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
