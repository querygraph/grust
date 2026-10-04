#!/usr/bin/env python3
"""Require the exact passing detached gate before committing the named branch."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
repo = Path('/private/tmp/sail-pecan-checkpoint-repartition')
source = json.loads((root / 'source-receipt.json').read_text())
receipt = json.loads(Path(sys.argv[1]).read_text())
assert receipt['outcome'] == 'passed' and receipt['source_and_runtime_hashes_unchanged']
assert receipt['source_head'] == source['base']
assert receipt['unit_tests'] == dict(tests=75, failures=0, errors=0, skipped=0)
assert receipt['sql_tests'] == dict(tests=4, failures=0, errors=0, skipped=0)
assert receipt['server_reaped']
assert subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == source['base']
assert subprocess.check_output(['git', '-C', str(repo), 'branch', '--show-current'], text=True).strip() == source['branch']
assert hashlib.sha256(subprocess.check_output(['git', '-C', str(repo), 'diff', '--cached', '--binary'])).hexdigest() == source['candidate_patch_sha256']
assert not subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only'])
for name, expected in source['files_sha256'].items():
    assert hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected, name
print('PECAN_CHECKPOINT_CANDIDATE_GATE PASSED b569+patch=' + source['candidate_patch_sha256'])
