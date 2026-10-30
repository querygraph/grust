"""Qualify the reference observations and retain every Sail parity difference."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
KEYS = ['name', 'definitions', 'query', 'consumer_conf']
EXPECTED = {
    'upstream_true': 'UNRESOLVED_COLUMN.WITH_SUGGESTION',
    'upstream_false_over_consumer_true': 'DUPLICATE_FLOW_SQL_CONF',
    'left_true_right_false': 'DUPLICATE_FLOW_SQL_CONF',
    'left_false_right_true': 'UNRESOLVED_COLUMN.WITH_SUGGESTION',
    'repeated_last_true': 'UNRESOLVED_COLUMN.WITH_SUGGESTION',
    'transitive_raw_conf': 'UNRESOLVED_COLUMN.WITH_SUGGESTION',
    'table_boundary': None,
    'same_value_compatible': None,
    'disjoint_keys_compatible': None,
    'transitive_conflict': 'DUPLICATE_FLOW_SQL_CONF',
    'nested_projection_before_last_false': 'DUPLICATE_FLOW_SQL_CONF',
    'scalar_subquery_last_true': 'DUPLICATE_FLOW_SQL_CONF',
    'external_read_after_true': 'UNRESOLVED_COLUMN.WITH_SUGGESTION',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def conditions(case):
    text = case.get('run_error', '') + '\n' + '\n'.join(e['message'] for e in case['events'])
    return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]', text)))


spark = json.loads((ROOT/'spark/observations.json').read_text())
sail = json.loads((ROOT/'sail/probe/observations.json').read_text())
assert spark['engine'] == 'spark' and sail['engine'] == 'sail'
for run in [spark, sail]:
    assert run['source_commit'] == '617618396087429b5627a86ce933bb0f5d6645cb'
    assert run['spark_version'] == '4.2.1' and run['outcome'] == 'observed'
    assert run['harness_sha256'] == digest(ROOT/'reference.py')
    assert len(run['cases']) == 13 and {c['name'] for c in run['cases']} == set(EXPECTED)
    assert not any('probe_error' in c for c in run['cases'])
    assert all(c['session_case_sensitive'] == 'false' for c in run['cases'])
assert spark['listener_probe_after_stop'] == {'exit_code': 1, 'stdout': ''}
receipt = json.loads((ROOT/'sail/receipt.json').read_text())
assert receipt['before'] == receipt['after']
assert receipt['before']['probe_sha256'] == digest(ROOT/'reference.py')
assert receipt['before']['sail_commit'] == '163b2fb52f9ba2961cd0338046d4d2f4cf91f686'
assert receipt['server_exit_code'] == receipt['probe_exit_code'] == 0
assert receipt['remaining_listener_pids'] == []
# The original directory nested observations under probe/; preserve that identity.
for item in receipt['files']:
    path = item['path']
    assert digest(ROOT/'sail'/path) == item['sha256']
rows = []
for reference, actual in zip(spark['cases'], sail['cases']):
    assert {k:reference[k] for k in KEYS} == {k:actual[k] for k in KEYS}
    expected = EXPECTED[reference['name']]
    assert conditions(reference) == ([] if expected is None else [expected])
    assert reference['run_returned'] == (expected is None)
    assert reference['result_exists'] == (expected is None)
    if expected is None:
        assert reference['rows'] == [{'foo' if reference['name']=='disjoint_keys_compatible' else 'Foo':1}]
    matched = (actual['run_returned'] == reference['run_returned'] and
               actual.get('rows') == reference.get('rows') and conditions(actual) == conditions(reference))
    rows.append({'name':reference['name'], 'spark_conditions':conditions(reference),
                 'sail_conditions':conditions(actual), 'spark_run_returned':reference['run_returned'],
                 'sail_run_returned':actual['run_returned'], 'matched': matched})
assert sum(row['matched'] for row in rows) == 3
assert sum(not row['matched'] for row in rows) == 10
print(json.dumps({'scope':'13 config probes only; no SDP acceptance', 'matched':3, 'mismatched':10, 'cases':rows},indent=2))
