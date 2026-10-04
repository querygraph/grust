#!/usr/bin/env python3
"""Read-only verification of public metadata and optional private raw sources."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify-private', action='store_true')
args = parser.parse_args()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
receipt = json.loads((base / 'verification.json').read_text())
actual = {p.name for p in base.iterdir() if p.is_file() and p.name != 'verification.json'}
assert actual == set(receipt['public_files'])
for name, record in receipt['public_files'].items():
    path = base / name
    assert path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], name
    if path.suffix == '.json':
        json.loads(path.read_text())
    if path.suffix == '.py':
        ast.parse(path.read_text(), filename=name)
exclusions = json.loads((base / 'publication-exclusions.json').read_text())
assert not any((base / item['original_file']).exists()
               for item in exclusions['excluded_from_publication'])
assert not list(base.glob('*.html'))
if args.verify_private:
    private = Path(exclusions['private_cache'])
    for name, record in exclusions['all_original_files_private_manifest'].items():
        path = private / name
        assert path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], name
samples = json.loads((base / 'tiny-sample-inspection.json').read_text())['objects']
assert len(samples) == 4 and sum(item['bytes'] for item in samples) == 1776
for item in samples:
    assert sha(base / item['file']) == item['sha256']
assert len(json.loads((base / 'parquet-url-inventory.json').read_text())['urls']) == 102
print(json.dumps({'outcome': 'passed', 'public_files_verified': len(actual),
                  'private_original_files_verified': 27 if args.verify_private else 0,
                  'scope': 'Identity verification only; no network or graph execution'}))
