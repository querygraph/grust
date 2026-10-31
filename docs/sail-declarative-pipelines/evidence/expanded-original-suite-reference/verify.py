from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

E = Path(__file__).resolve().parent
R = '/Users/alexy/src/grust-sdp'
S = '/Users/alexy/src/spark-sdp-4.2.1'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

for path, h in json.loads((E / 'MANIFEST.json').read_text()).items():
    assert sha(E / path) == h, path
summary = json.loads((E / 'summary.json').read_text())
assert not summary['sail_executed']
collect = json.loads((E / 'qualified/collect/receipt.json').read_text())
assert collect['outcome'] == 'passed' and len(collect['bindings']) == 56
for name, h in collect['tool_sha256'].items():
    data = subprocess.check_output(['git', '-C', R, 'show', summary['tool_commit'] + ':scripts/sdp-scala-reference/' + name])
    assert hashlib.sha256(data).hexdigest() == h
for binding in collect['bindings']:
    data = subprocess.check_output(['git', '-C', S, 'show', summary['spark_commit'] + ':' + binding['source']])
    assert hashlib.sha256(data).hexdigest() == binding['sha256']
rows = json.loads((E / 'qualified/collect/suites.json').read_text())
assert sum(bool(r['testNames']) for r in rows) == 43
assert sum(len(r['testNames']) for r in rows) == 595
assert not any(r['status'] == 'unresolved' or r['nestedSuiteIds'] for r in rows)
assert not any('org.scalatest.Ignore' in tags for r in rows for tags in r['tags'].values())
for path, h in collect['output_sha256'].items():
    assert sha(E / 'qualified/collect' / path) == h
for name, count in summary['counts'].items():
    root = E / name if name.startswith('lifecycle-') else E / 'qualified' / name
    receipt = json.loads((root / 'receipt.json').read_text())
    assert receipt['outcome'] == 'passed'
    assert receipt['tool_sha256'] == collect['tool_sha256']
    assert receipt['runtime_sha256'] == collect['runtime_sha256']
    for check in receipt['checks']:
        assert check['exit_code'] == 0 and sha(root / check['log']) == check['sha256']
    cases = [t for p in (root / 'xml').glob('*.xml') for t in ET.parse(p).iter('testcase')]
    assert len(cases) == count and all(not list(t) for t in cases)
    for path, h in receipt['output_sha256'].items():
        assert sha(root / path) == h
assert sum(summary['counts'].values()) == 99
print('PASS expanded Spark reference: 56 bindings,595 names,99 executions; no Sail acceptance')
D = E.parent.parent
# This packet's counters describe its immutable qualification snapshot.
SNAPSHOT = 'e14f64dcdc5ddebcac628706237177037b64ecf2'
current = json.loads(subprocess.check_output(['git', '-C', R, 'show', SNAPSHOT + ':docs/sail-declarative-pipelines/spark-4.2.1-inventory.json']))
legacy = json.loads(subprocess.check_output(['git', '-C', R, 'show', '3806b1bc58cf466c5146ca0f6829a3632701aaec:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json']))
expansion = json.loads(subprocess.check_output(['git', '-C', R, 'show', SNAPSHOT + ':docs/sail-declarative-pipelines/spark-4.2.1-scope-expansion.json']))
old = {c['id']: c for c in legacy['cases']}
new = {c['id']: c for c in current['cases']}
assert len(new) == 486 and len(current['source_sha256']) == 56
assert all(new[k] == c for k, c in old.items())
assert set(new) - set(old) == {c['id'] for c in expansion['cases']}
assert expansion['canonical_reconciled'] and len(expansion['cases']) == 24
assert sum('coverage_review' in c for c in new.values()) == 100
assert sum(c['status'] == 'partial-behavioral-port' for c in new.values()) == 71
assert sum(c['status'] == 'unmapped' for c in new.values()) == 415
assert expansion['completion_blocker'] and not expansion['owned_runtime_is_complete_goal_denominator']
print('PASS canonical486 with462 prior records unchanged,24 additions,100 reviewed,71 partial415 unmapped')
