#!/usr/bin/env python3
"""Read-only inventory audit of the exact follow-up union, with no builds."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = 'b569e75de625885b3d919fa4196b2e0bed14c618'
NATIVE = 'b4babe87cb50d16b4d439a0841a6291991c433d2'
BENCHMARK = 'c8fe857848f3ba1698ee0f9d1daf000790d691d4'
PECAN = 'fe44428c9bfb43680affed0abae07240220df852'
TREE = 'fd33c56019a00205ce5588760d744b6bdb132b58'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exact-head')
    args = parser.parse_args()

    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(args.repo), *arguments])

    def inventory(ref):
        result = {}
        for record in git('ls-tree', '-rz', ref).split(b'\0'):
            if record:
                meta, path = record.split(b'\t', 1)
                mode, kind, blob = meta.split()
                result[path.decode()] = [mode.decode(), blob.decode()]
        return result

    def index():
        result = {}
        for record in git('ls-files', '--stage', '-z').split(b'\0'):
            if record:
                meta, path = record.split(b'\t', 1)
                mode, blob, stage = meta.split()
                assert stage == b'0', 'unmerged index entry'
                result[path.decode()] = [mode.decode(), blob.decode()]
        return result

    head = git('rev-parse', 'HEAD').decode().strip()
    assert not git('diff', '--name-only'), 'unstaged changes'
    assert not git('ls-files', '--others', '--exclude-standard'), 'untracked files'
    if args.exact_head:
        assert head == args.exact_head
        assert git('rev-parse', 'HEAD^{tree}').decode().strip() == TREE
        assert not git('status', '--porcelain'), 'exact commit is dirty'
    base, native, benchmark, pecan = map(inventory, (BASE, NATIVE, BENCHMARK, PECAN))
    expected = dict(native)
    changes = {}
    for label, source, prefix in (
            ('benchmark', benchmark, 'examples/extensions/benchmarks/'),
            ('pecan', pecan, 'examples/extensions/graph-algorithms/')):
        changed = {p for p in set(source) | set(base) if source.get(p) != base.get(p)}
        assert all(p.startswith(prefix) for p in changed), (label, changed)
        changes[label] = sorted(changed)
        for path in changed:
            if path in source:
                expected[path] = source[path]
            else:
                expected.pop(path)
    actual = index()
    assert actual == expected, sorted(p for p in set(actual) | set(expected) if actual.get(p) != expected.get(p))
    assert actual == inventory(TREE), 'frozen tree differs'
    hydrated_lfs = []
    for path, entry in actual.items():
        # Compute Git SHA-1 blobs in process; no object writes or filters invoked.
        if entry[0] != '160000':
            file = args.repo / path
            data = os.fsencode(os.readlink(file)) if entry[0] == '120000' else file.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if blob != entry[1]:
                pointer = git('cat-file', 'blob', entry[1]).decode().splitlines()
                assert pointer == ['version https://git-lfs.github.com/spec/v1',
                                   'oid sha256:' + hashlib.sha256(data).hexdigest(),
                                   'size ' + str(len(data))], path
                hydrated_lfs.append(path)
    host = {p: b for p, b in base.items() if not p.startswith('examples/')}
    assert {p: b for p, b in actual.items() if not p.startswith('examples/')} == host
    proofs = []
    for label, source, prefix in (
            ('all host source and metadata outside examples', base, None),
            ('Argentea core', native, 'examples/extensions/argentea/'),
            ('native adapter', native, 'examples/extensions/nutmeg/'),
            ('benchmark harness', benchmark, 'examples/extensions/benchmarks/'),
            ('Pecan controller and tests', pecan, 'examples/extensions/graph-algorithms/')):
        want = host if prefix is None else {p: b for p, b in source.items() if p.startswith(prefix)}
        have = {p: b for p, b in actual.items() if (not p.startswith('examples/') if prefix is None else p.startswith(prefix))}
        assert want == have, label
        proofs.append({'scope': label, 'files': len(have), 'all_equal': True})
    assert index() == actual and git('rev-parse', 'HEAD').decode().strip() == head
    receipt = {
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'outcome': 'PASS_SOURCE_AUDIT', 'head': head, 'tree': TREE,
        'scope': 'exact commit' if args.exact_head else 'frozen staged candidate, not a commit verdict',
        'source_commits': {'base': BASE, 'native': NATIVE, 'benchmark': BENCHMARK, 'pecan': PECAN},
        'full_tree_equals_exact_expected_union': True, 'tracked_files': len(actual),
        'hydrated_lfs_files_verified_by_pointer_sha256_and_size': hydrated_lfs,
        'source_proofs': proofs, 'overlay_changed_paths': changes,
        'source_inventory_sha256': hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'review_findings': [],
        'limits': [
            'Read-only inventory and source interaction review; no test or compile execution by independent auditor',
            'Host Rust is byte-identical to b569, not freshly qualified by 490 host Rust tests on this union',
            'Native ordinary/loaded tests and Python/SQL gates are separate receipts owned by integrating agent',
            'Installed local SQL runtime is identified by bytes, not claimed built from this candidate',
            'No Linux process-cluster or full WCC qualification, default promotion or performance claim',
            'Prior independent WCC protocol counterexamples apply through exact c8 source identity; no new duplicated counterexample run']}
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'outcome':receipt['outcome'], 'head':head, 'tree':TREE,
                      'receipt_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
