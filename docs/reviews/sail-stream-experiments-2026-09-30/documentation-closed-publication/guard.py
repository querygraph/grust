"""Bind documentation gates to the independently reviewed detached candidate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/private/tmp/grust-sail-review-closed-docs')
OUT = Path('/private/tmp/grust-sail-review-closed-publication')
PIN = json.loads((OUT/'frozen.json').read_text())

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

audit_pin = json.loads((OUT/'audit-pin.json').read_text())
audit_path = OUT/'independent-audit.json'
assert sha(audit_path) == audit_pin['sha256']
audit = json.loads(audit_path.read_text())
assert audit['outcome'] == 'PASS_INDEPENDENT_PUBLICATION_AUDIT'
assert audit['frozen_index_tree'] == PIN['tree']
assert audit['manifest_sha256'] == PIN['manifest_sha256']
phase = sys.argv[1]
expected = PIN['base'] if phase.startswith('candidate') else sys.argv[2]
assert git('rev-parse', 'HEAD') == expected
assert subprocess.run(['git', '-C', str(ROOT), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
assert git('write-tree') == PIN['tree']
assert subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet']).returncode == 0
assert not git('ls-files', '--others', '--exclude-standard')
assert sha(ROOT/PIN['manifest_path']) == PIN['manifest_sha256']
if phase.startswith('exact'):
    assert git('rev-parse', 'HEAD^{tree}') == PIN['tree']
    assert not git('status', '--porcelain')
    assert git('rev-parse', 'HEAD^') == PIN['base']
if phase.endswith('after'):
    log = OUT/('candidate-gate.log' if phase.startswith('candidate') else 'exact-gate.log')
    data = log.read_text()
    assert data.endswith('SAIL_REVIEW_DOCUMENTATION PASSED ' + expected + '\n')
    stats = json.loads(data[:data.rindex('\nSAIL_REVIEW_DOCUMENTATION')])
    assert stats['manifest_sha256'] == PIN['manifest_sha256']
    receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), phase=phase,
        head=expected, tree=PIN['tree'], gate=stats, gate_log_sha256=sha(log), verdict='PASS',
        scope='Documentation snapshot integrity only; no runtime gate or performance qualification.')
    (OUT/(phase+'-receipt.json')).write_text(json.dumps(receipt, indent=2)+'\n')
print('DOCUMENTATION_SOURCE_GUARD PASSED ' + phase + ' ' + expected + ' ' + PIN['tree'])
