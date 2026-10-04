"""Bind candidate/exact documentation gates to independent frozen-source review."""
import argparse
from common import *

parser = argparse.ArgumentParser()
parser.add_argument('phase', choices=['candidate-before', 'candidate-after', 'exact-before', 'exact-after'])
parser.add_argument('head', nargs='?')
a = parser.parse_args()
pin = load(OUT/'frozen.json')
check(pin['base'] == BASE, 'unexpected publication base')
check(sha(OUT/'preparation.json') == pin['preparation_sha256'], 'preparation receipt changed')
check(sha(OUT/'base-manifest.json') == pin['base_manifest_sha256'], 'base manifest changed')
prep = load(OUT/'preparation.json')
audit_pin = load(OUT/'audit-pin.json')
check(sha(OUT/'independent-audit.json') == audit_pin['sha256'], 'independent audit changed')
audit = load(OUT/'independent-audit.json')
check(audit['outcome'] == 'PASS_INDEPENDENT_PUBLICATION_AUDIT', 'independent audit did not pass')
check(audit['frozen_index_tree'] == pin['tree'] and audit['manifest_sha256'] == pin['manifest_sha256'],
      'independent audit names another snapshot')
expected = BASE if a.phase.startswith('candidate') else a.head
check(expected and len(expected) == 40, 'exact commit required')
source_guard(pin, prep, a.phase, expected)
shared = check_shared(prep)
if a.phase.endswith('after'):
    log = OUT/('candidate-gate.log' if a.phase.startswith('candidate') else 'exact-gate.log')
    data = log.read_text()
    check(data.endswith('SAIL_REVIEW_DOCUMENTATION PASSED '+expected+'\n'), 'documentation gate lacks exact verdict')
    stats = json.loads(data[:data.rindex('\nSAIL_REVIEW_DOCUMENTATION')])
    check(stats['manifest_sha256'] == pin['manifest_sha256'], 'gate read another manifest')
    write_new(OUT/(a.phase+'-receipt.json'), dict(recorded_utc=utc(), phase=a.phase,
        head=expected, tree=pin['tree'], gate=stats, gate_log_sha256=sha(log), verdict='PASS',
        shared_observation=shared, scope='Documentation integrity only; not a runtime or performance gate.'))
print('DOCUMENTATION_SOURCE_GUARD PASSED', a.phase, expected, pin['tree'])
