"""Compare identical public inputs; preserve the five structured-error differences."""
from pathlib import Path
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent/'flow-config-fusion-reference'
RUN = HERE/sys.argv[1]
COMMIT = sys.argv[2]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def conditions(case):
    message = case.get('run_error', '')+'\n'+'\n'.join(event['message'] for event in case['events'])
    return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]', message)))
spark = json.loads((REFERENCE/'spark/observations.json').read_text())
sail = json.loads((RUN/'probe/observations.json').read_text())
receipt = json.loads((RUN/'receipt.json').read_text())
assert receipt['before'] == receipt['after']
assert receipt['before']['sail_commit'] == COMMIT
assert receipt['before']['probe_sha256'] == digest(HERE/'reference.py')
assert digest(HERE/'reference.py') == digest(REFERENCE/'reference.py')
assert receipt['server_exit_code'] == receipt['probe_exit_code'] == 0
assert receipt['remaining_listener_pids'] == []
for item in receipt['files']:
    assert digest(RUN/item['path']) == item['sha256']
for run in [spark, sail]:
    assert run['spark_version'] == '4.2.1' and run['outcome'] == 'observed'
    assert len(run['cases']) == 13
    assert run['source_commit'] == '617618396087429b5627a86ce933bb0f5d6645cb'
    assert all(c['session_case_sensitive'] == 'false' for c in run['cases'])
    assert not any('probe_error' in c for c in run['cases'])
keys = ['name', 'definitions', 'query', 'consumer_conf']
rows = []
for expected, actual in zip(spark['cases'], sail['cases']):
    assert {key:expected[key] for key in keys} == {key:actual[key] for key in keys}
    matched = (actual['run_returned'] == expected['run_returned'] and actual.get('rows') == expected.get('rows') and actual['result_exists'] == expected['result_exists'] and conditions(actual) == conditions(expected))
    rows.append({'name':actual['name'], 'spark_conditions':conditions(expected), 'sail_conditions':conditions(actual), 'matched':matched})
assert sum(row['matched'] for row in rows) == 8
assert {row['name'] for row in rows if not row['matched']} == {'upstream_true','left_false_right_true','repeated_last_true','transitive_raw_conf','external_read_after_true'}
assert all(row['spark_conditions'] == ['UNRESOLVED_COLUMN.WITH_SUGGESTION'] and row['sail_conditions'] == [] for row in rows if not row['matched'])
print(json.dumps({'sail_commit':COMMIT,'scope':'13 identical public probes: error conditions and success rows only, not full parameter/message equivalence or Scala acceptance','matched':8,'mismatched':5,'cases':rows},indent=2))
