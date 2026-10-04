"""Bind documentation gates to the independently reviewed detached candidate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/private/tmp/grust-sail-review-closed2-docs')
OUT = Path('/private/tmp/grust-sail-review-closed2-publication')
PIN = json.loads((OUT/'frozen.json').read_text())

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Check only the frozen source allowlist; later unique observations are excluded.
PREP = json.loads((OUT/'preparation.json').read_text())
assert sha(OUT/'preparation.json') == PIN['preparation_sha256']
SHARED = Path('/Users/alexy/src/grust')
def info(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size, mode=oct(path.stat().st_mode & 0o777))
def shared_git(*args):
    return subprocess.check_output(['git', '-C', str(SHARED), *args], text=True).strip()
shared_index = Path(shared_git('rev-parse', '--path-format=absolute', '--git-path', 'index'))
shared_now = dict(head=shared_git('rev-parse', 'HEAD'), index=info(shared_index),
    coordination=info(SHARED/'codex-to-codex.md'),
    prose=info(SHARED/'docs/reviews/sail-stream-experiments-2026-09-30/RESULTS.md'),
    response=info(SHARED/'docs/reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-RESPONSE.md'))
assert shared_now == PREP['shared_before'], 'shared checkout moved'
for relative, expected_info in PREP['selected_sources'].items():
    assert not (SHARED/relative).is_symlink() and info(SHARED/relative) == expected_info, relative
    assert not (ROOT/relative).is_symlink() and info(ROOT/relative) == expected_info, relative

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
