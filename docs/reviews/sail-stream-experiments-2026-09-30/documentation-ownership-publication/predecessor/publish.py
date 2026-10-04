"""Publish the exact gated direct child using atomic, FF-proven two-ref CAS."""
from common import *

pin = load(OUT/'frozen.json')
check(not (OUT/'delivery.json').exists(), 'publication already attempted')
check(pin['expected_remote_refs'] == dict.fromkeys(REFS, BASE), 'unexpected publication refs/base')
head = git(DST, 'rev-parse', 'HEAD')
subprocess.run(['python3', str(OUT/'guard.py'), 'exact-before', head], check=True, env=ENV)
gate = load(OUT/'exact-after-receipt.json')
check(gate['head'] == head and gate['tree'] == pin['tree'] and gate['verdict'] == 'PASS', 'wrong exact gate')
check(gate['gate_log_sha256'] == sha(OUT/'exact-gate.log'), 'exact gate log changed')
check(git(DST, 'rev-parse', 'HEAD^') == BASE, 'only direct-child fast-forward allowed')
before = remote_refs()
check(before == pin['expected_remote_refs'], 'remote refs advanced; no overwrite permitted')
for old in before.values():
    subprocess.run(['git', '-C', str(DST), 'merge-base', '--is-ancestor', old, head], check=True, env=ENV)
command = ['git', '-C', str(DST), 'push', '--atomic',
           *[f'--force-with-lease={ref}:{BASE}' for ref in REFS], 'origin', *[f'{head}:{ref}' for ref in REFS]]
receipt = dict(started_utc=utc(), base_commit=BASE, commit=head, tree=pin['tree'], remote_before=before,
               push_command=command, scope=pin['scope'])
write_new(OUT/'publication-intent.json', receipt)
try:
    result = subprocess.run(command, env=ENV, capture_output=True, timeout=180)
    (OUT/'push.stdout').write_bytes(result.stdout)
    (OUT/'push.stderr').write_bytes(result.stderr)
    receipt['push_returncode'] = result.returncode
    result.check_returncode()
    receipt['remote_after'] = remote_refs()
    check(receipt['remote_after'] == dict.fromkeys(REFS, head), 'post-push refs differ')
    receipt.update(verdict='DELIVERED_EXACT_DOCUMENTATION_GATE_PASS', gate=gate,
                   independent_audit_sha256=sha(OUT/'independent-audit.json'),
                   shared_after=check_shared(load(OUT/'preparation.json')),
                   guards='Direct parent and both ancestry proofs establish fast-forward. Atomic explicit leases compare-and-swap both refs; no shared branch/index activation.')
except BaseException as error:
    receipt.update(verdict='PUBLICATION_FAILED_OR_UNCERTAIN', error=repr(error))
    if isinstance(error, subprocess.TimeoutExpired):
        (OUT/'push-timeout.stdout').write_bytes(error.stdout or b'')
        (OUT/'push-timeout.stderr').write_bytes(error.stderr or b'')
    raise
finally:
    receipt['finished_utc'] = utc()
    write_new(OUT/'delivery.json', receipt)
print(json.dumps(dict(commit=head, verdict=receipt['verdict'], remote_after=receipt['remote_after'])))
