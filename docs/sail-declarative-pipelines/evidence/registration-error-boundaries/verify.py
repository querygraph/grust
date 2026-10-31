from pathlib import Path
import collections
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

E = Path(__file__).resolve().parent
S = '/Users/alexy/src/sail-pipelines-proposal'
R = '/Users/alexy/src/grust-sdp'
SP = '/Users/alexy/src/spark-sdp-4.2.1'
def read(path):
    return json.loads((E / path).read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def tests(root, expected):
    cases = [t for p in root.glob('*.xml') for t in ET.parse(p).iter('testcase')]
    assert len(cases) == expected and all(not list(t) for t in cases), root
    return cases

for path, h in read('MANIFEST.json').items():
    assert sha(E / path) == h, path
summary = read('summary.json')
assert not summary['full_conformance'] and not summary['original_scala_suite_executed_on_sail']
gate = read('native/sail-sdp-raw-flow-name-01-gate.json')
assert gate['sail_commit'] == summary['sail_commit'] and gate['outcome'] == 'passed'
for check in gate['checks']:
    assert check['exit_code'] == 0 and sha(E / 'native' / Path(check['log']).name) == check['sha256']
assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed;', (E / 'native/sail-sdp-raw-flow-name-01-rust.log').read_text()))) == 279
public = read('public/receipt.json')
assert public['outcome'] == 'passed' and public['sail_commit'] == summary['sail_commit']
assert not public['remaining_listener_pids']
assert public['pytest'] == dict(tests=300, failures=0, errors=0, skipped=0)
tests(E / 'public', 300)
u = read('public/upstream.json')
assert u['tests_run'] == 67 and not u['failures'] and not u['errors'] and not u['skipped']
for mode in ['spark', 'sail']:
    root = E / (mode + '-feature')
    record = json.loads((root / 'observations.json').read_text())
    assert record['version'] == '4.2.1' and record['pytest_exit_code'] == 0 and not record['remaining_listeners']
    tests(root, 21)
    source = subprocess.check_output(['git', '-C', S, 'show', summary['sail_commit'] + ':python/pysail/tests/spark/pipelines/test_flow_name_errors.py'])
    assert hashlib.sha256(source).hexdigest() == record['test_sha256']
a = read('spark-feature/observations.json')
b = read('sail-feature/observations.json')
assert len(a['cases']) == len(b['cases']) == 12
for x, y in zip(a['cases'], b['cases']):
    for key in ['api', 'name', 'implicit', 'outcome', 'error_type', 'condition', 'sql_state', 'parameters']:
        assert x.get(key) == y.get(key), (key, x, y)
assert sum(c['outcome'] == 'accepted' for c in a['cases']) == 3
parent = read('names-parent/observations.json')
assert parent['runtime_commit'] == summary['base'] and len(parent['cases']) == 12
assert sum(x.get('condition') != y.get('condition') or x.get('error_type') != y.get('error_type') for x, y in zip(a['cases'], parent['cases'])) == 9
for mode in ['spark', 'sail']:
    r = read('unicode-' + mode + '/observations.json')
    assert not r['remaining_listeners'] and len(r['cases']) == 4
    spellings = {'`ΣΔ`.`雪`': 'ΣΔ.雪', '`é.dot`.`雪``Q`': 'é.dot.雪`Q'}
    for c in r['cases']:
        expected = spellings[c['name']] if c['api'] == 'sql' else c['name']
        assert c['error_type'] == 'AnalysisException' and c['condition'] == 'MULTIPART_FLOW_NAME_NOT_SUPPORTED' and c['sql_state'] == '0A000'
        assert c['parameters'] == {'flowName': expected}
old = read('registration-parent/observations.json')
oracle = read('registration-spark/observations.json')
wrapped = 0
for x, y in zip(oracle['cases'], old['cases']):
    if x['condition'] == y['condition'] == 'PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR':
        wrapped += 1
        for key in ['offendingQuery', 'codeLocation']:
            assert x['parameters'][key] == y['parameters'][key]
assert wrapped == 10
classified = read('classified-regression/observations.json')
assert classified['pytest_exit_code'] == 0 and not classified['remaining_listeners']
tests(E / 'classified-regression', 4)
assert classified['cases'][2]['parameters'] == {}
for name in ['name', 'metadata', 'commit']:
    c = read('control-' + name + '.json')
    assert c['base'] == summary['sail_commit'] and c['exit_code'] == 101
    log = E / ('control-' + name + '.log')
    assert sha(log) == c['log_sha256'] and '0 passed; 1 failed;' in log.read_text()
    assert subprocess.check_output(['git', '-C', S, 'diff', '--name-only', c['base'], c['control']], text=True).strip() == c['path']
    for rev in [c['base'], c['control']]:
        assert subprocess.check_output(['git', '-C', S, 'rev-parse', rev + ':' + c['test_path']], text=True).strip() == c['test_blob']
reference = read('reference-sql-suite/receipt.json')
assert reference['outcome'] == 'passed' and reference['source_pin'] == summary['spark_commit'] and len(reference['bindings']) == 56
collect_root = E.parent / 'expanded-original-suite-reference/qualified/collect'
collect = json.loads((collect_root / 'receipt.json').read_text())
assert reference['tool_sha256'] == collect['tool_sha256'] and reference['runtime_sha256'] == collect['runtime_sha256']
for name, h in reference['tool_sha256'].items():
    data = subprocess.check_output(['git', '-C', R, 'show', summary['reference_gate_commit'] + ':scripts/sdp-scala-reference/' + name])
    assert hashlib.sha256(data).hexdigest() == h
for binding in reference['bindings']:
    data = subprocess.check_output(['git', '-C', SP, 'show', reference['source_pin'] + ':' + binding['source']])
    assert hashlib.sha256(data).hexdigest() == binding['sha256']
for check in reference['checks']:
    assert check['exit_code'] == 0 and sha(E / 'reference-sql-suite' / check['log']) == check['sha256']
for path, h in reference['output_sha256'].items():
    assert sha(E / 'reference-sql-suite' / path) == h
cases = tests(E / 'reference-sql-suite/xml', 43)
rows = json.loads((collect_root / 'suites.json').read_text())
row = next(r for r in rows if r['className'] == 'org.apache.spark.sql.pipelines.graph.SqlPipelineSuite')
assert {c.attrib['name'] for c in cases} == set(row['testNames'])
assert any(c.attrib['name'] == 'Flow cannot be created with multipart identifier' for c in cases)
assert summary['total_original_reference_executions'] == 99 + len(cases) == 142
inventory = read('inventory-snapshot.json')
old_inventory = json.loads(subprocess.check_output(['git', '-C', R, 'show', '667236f4a9c79123941618ca361f33285ecad0e8:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json']))
now = {c['id']: c for c in inventory['cases']}
assert len(now) == 486
for c in old_inventory['cases']:
    if c['id'] != summary['changed_existing_inventory_id']:
        assert c == now[c['id']], c['id']
assert now[summary['changed_existing_inventory_id']]['coverage_review']['runtime_commit'] == summary['sail_commit']
assert sum('coverage_review' in c for c in now.values()) == 116
assert dict(collections.Counter(c['status'] for c in now.values())) == {'unmapped': 399, 'partial-behavioral-port': 87}
print('PASS raw Flow279-native/300+67/paired21/Unicode4/classified4/three controls;original Spark SQL43,total142;one existing coverage improvement')
