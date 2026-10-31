from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

E = Path(__file__).resolve().parent
S = '/Users/alexy/src/sail-pipelines-proposal'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads((E / p).read_text())
def cases(p, count):
    tests = list(ET.parse(E / p).iter('testcase'))
    assert len(tests) == count and all(not list(t) for t in tests), p
for p, h in read('MANIFEST.json').items():
    assert sha(E / p) == h, p
for label, commit, count in [('direct-pipeline-ddl-01', '25173ed903162e0f9928b4501a3eac98c999b291', 224), ('direct-flow-ddl-02', 'c50ef22530a42a48aac330252a4d14ab239527e6', 225)]:
    g = read(label + '/sail-sdp-' + label + '-gate.json')
    assert g['outcome'] == 'passed' and g['sail_commit'] == commit
    for c in g['checks']:
        assert c['exit_code'] == 0 and sha(E / label / Path(c['log']).name) == c['sha256']
    log = (E / label / ('sail-sdp-' + label + '-rust.log')).read_text()
    import re
    assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed;', log))) == count
for phase, count in [('dataset', 2), ('flow', 3)]:
    receipt = read(phase + '/public/receipt.json')
    assert receipt['outcome'] == 'passed'
    cases(phase + '/public/pytest.xml', 300)
    observations = [read(phase + '/' + engine + '/observations.json') for engine in ['spark', 'sail']]
    for engine, r in zip(['spark', 'sail'], observations):
        assert r['pytest_exit_code'] == 0 and not r['remaining_listeners']
        cases(phase + '/' + engine + '/pytest.xml', count + (phase == 'flow' and engine == 'sail'))
    for a, b in zip(*(r['cases'] for r in observations)):
        for k in ['kind', 'sql', 'outcome', 'error_type', 'condition', 'sql_state', 'parameters']:
            assert a[k] == b[k], (phase, k)
failed = read('flow/failed-extra-row-assumption/observations.json')
assert failed['pytest_exit_code'] != 0 and not failed['remaining_listeners']
iso = read('flow/isolated-effect/observations.json')
assert iso['version'] == '4.2.1' and not iso['remaining_listeners']
f = iso['cases'][0]
assert f['before_rows'] == {'table1': [[1]], 'table2': [[2]]}
assert f['condition'] == 'UNSUPPORTED_FEATURE.CREATE_FLOW_QUERY_EXECUTION'
assert sorted(f['rows']['table2']) == [[1], [2]]
for name in ['guard', 'hierarchy']:
    c = read('direct-ddl-' + name + '-control.json')
    assert c['exit_code'] == 101 and sha(E / ('direct-ddl-' + name + '-control.log')) == c['log_sha256']
    assert '0 passed; 1 failed;' in (E / ('direct-ddl-' + name + '-control.log')).read_text()
c = read('direct-flow-ddl-flow-control.json')
assert c['exit_code'] == 101 and sha(E / 'direct-flow-ddl-flow-control.log') == c['log_sha256']
for c in [c, read('direct-ddl-guard-control.json'), read('direct-ddl-hierarchy-control.json')]:
    diff = subprocess.check_output(['git', '-C', S, 'diff', '--name-only', c['base'], c['control']], text=True).strip()
    assert diff == c['path']
    for rev in [c['base'], c['control']]:
        assert subprocess.check_output(['git', '-C', S, 'rev-parse', rev + ':' + c['test_path']], text=True).strip() == c['test_blob']
print('PASS direct declaration diagnostics, public ports, unchanged-test controls and preserved row-effect counterexample')
