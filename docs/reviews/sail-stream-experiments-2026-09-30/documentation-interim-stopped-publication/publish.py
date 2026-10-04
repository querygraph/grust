"""Publish only the exact gated child of the unchanged pair of remote refs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/private/tmp/grust-sail-review-interim-docs')
O = Path('/private/tmp/grust-sail-review-interim-publication')
PIN = json.loads((O/'frozen.json').read_text())
REFS = ['refs/heads/work/proposal-v5', 'refs/heads/work/sail-graph-review']

def git(*args):
    return subprocess.check_output(['git', '-C', str(R), *args], text=True).strip()

def remote():
    return {line.split()[1]: line.split()[0] for line in git('ls-remote', 'origin', *REFS).splitlines()}

head = git('rev-parse', 'HEAD')
assert git('rev-parse', 'HEAD^') == PIN['base'], 'only the exact direct-child fast-forward is allowed'
assert git('rev-parse', 'HEAD^{tree}') == PIN['tree']
assert not git('status', '--porcelain')
subprocess.run(['python3', str(O/'guard.py'), 'exact-before', head], check=True)
gate = json.loads((O/'exact-after-receipt.json').read_text())
assert gate['head'] == head and gate['verdict'] == 'PASS'
before = remote()
assert before == dict.fromkeys(REFS, PIN['base']), before
# Leases provide compare-and-swap, not permission for a non-fast-forward:
# the direct-parent guard above proves both intended updates are fast-forwards.
command = ['git', '-C', str(R), 'push', '--atomic',
           *[f'--force-with-lease={ref}:{PIN["base"]}' for ref in REFS],
           'origin', *[f'{head}:{ref}' for ref in REFS]]
receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(), repository='querygraph/grust',
    base_commit=PIN['base'], commit=head, tree=PIN['tree'], remote_before=before, push_command=command)
try:
    result = subprocess.run(command, text=True, capture_output=True, timeout=180)
    (O/'push.stdout').write_text(result.stdout)
    (O/'push.stderr').write_text(result.stderr)
    receipt['push_returncode'] = result.returncode
    result.check_returncode()
    after = remote()
    receipt['remote_after'] = after
    assert after == dict.fromkeys(REFS, head), after
    receipt.update(verdict='DELIVERED_EXACT_DOCUMENTATION_GATE_PASS', gate=gate,
        independent_audit_sha256=hashlib.sha256((O/'independent-audit.json').read_bytes()).hexdigest(),
        candidate_shared_prose_differences=PIN['candidate_only_prose_differences'],
        frozen_observation_cutoff=PIN['cutoff'],
        guards='Clean detached exact tested SHA and direct parent prove fast-forward; both old refs checked and leased atomically; exact remote refs verified after. Shared HEAD/index/prose/branches not activated.',
        scope='Completed interim observations only; logging02 remains active, not a final replay result. No runtime release, new measurement or performance qualification.')
except BaseException as error:
    receipt.update(verdict='PUBLICATION_FAILED_OR_UNCERTAIN', error=repr(error))
    raise
finally:
    receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (O/'delivery.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(dict(commit=head, remote_after=receipt['remote_after'], verdict=receipt['verdict']), indent=2))
