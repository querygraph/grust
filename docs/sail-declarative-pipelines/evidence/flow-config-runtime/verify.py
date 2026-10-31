"""Verify immutable evidence identities; this is not a full SDP acceptance gate."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SAIL = '/Users/alexy/src/sail-pipelines-proposal'
FINAL = '1bc9d15620dd4c85ac3f09ff8ec90d5b92a4292e'
TRACE = 'fa78d067cd20c9ca3a3d1c29055eeb53633a22bd'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):
    return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
manifest = json.loads((HERE/'SHA256.json').read_text())
assert set(manifest) == {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name != 'SHA256.json'}
for path, expected in manifest.items():
    assert digest(HERE/path) == expected, path
for folder, sha, counts in [
    ('source-read-case-ready','b4d83ef728910a00e8564c1991c8024a9a22fc15',[88,151]),
    ('config-merge-import','349771bd9445eb847904ce57659ab8baf07a315c',[88,166]),
    ('flow-config-runtime-ready','34b80b2a015533dbf9a20d6437d60ebbf14e8115',[88,173]),
    ('flow-config-runtime-counted','c43bfd68e31e8c5c98484f954879c5944699a994',[88,174]),
    ('flow-config-runtime-native','17d671c987477903eaa307d07748e52a9b692d18',[88,176]),
    ('flow-config-trace',TRACE,[88,170]),
    ('flow-config-activation',FINAL,[88,176]),
]:
    base = HERE/folder
    candidate = json.loads((base/'candidate.json').read_text())
    gate = json.loads((base/'gate.json').read_text())
    assert candidate['commit'] == gate['sail_commit'] == sha
    assert gate['outcome'] == 'passed'
    assert [c['name'] for c in gate['checks']] == ['fmt','clippy','rust']
    assert all(c['exit_code'] == 0 for c in gate['checks'])
    for check in gate['checks']:
        assert digest(base/(check['name']+'.log')) == check['sha256']
    found = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (base/'rust.log').read_text())
    assert [int(n) for n in found] == counts, (folder, found)
    assert git('rev-parse',sha+'^') == candidate['base']
assert git('rev-parse',FINAL+'^') == TRACE
assert git('rev-parse',FINAL+'^{tree}') == git('rev-parse','17d671c98^{tree}')
for name in ['getter','view']:
    data = json.loads((HERE/'native-controls'/(name+'.json')).read_text())
    assert data['exit_code'] == 101
    assert digest(HERE/'native-controls'/(name+'.log')) == data['log_sha256']
    assert '0 passed; 2 failed;' in (HERE/'native-controls'/(name+'.log')).read_text()
regression = HERE/'flow-config-native-regression'
assert '0 passed; 2 failed;' in (regression/'rust.log').read_text()
test_path = 'crates/sail-spark-connect/src/pipelines/config/runtime_tests.rs'
assert git('rev-parse','38abecd84:'+test_path) == git('rev-parse',FINAL+':'+test_path)
for folder, sha in [('flow-config-public-c43bfd68e','c43bfd68e31e8c5c98484f954879c5944699a994'),('flow-config-public-1bc9d1562',FINAL)]:
    base = HERE/folder
    data = json.loads((base/'receipt.json').read_text())
    assert data['sail_commit'] == sha and data['before'] == data['after']
    assert data['before']['head'] == sha and data['outcome'] == 'passed'
    assert data['server_exit_code'] == 0 and data['remaining_listener_pids'] == []
    assert all(c['exit_code'] == 0 for c in data['checks'])
    assert data['pytest'] == {'tests':300,'failures':0,'errors':0,'skipped':0}
    assert data['upstream'] == {'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
    suite = ET.parse(base/'pytest.xml').getroot().find('testsuite')
    assert suite is not None and [int(suite.get(k)) for k in ['tests','failures','errors','skipped']] == [300,0,0,0]
    for path, expected in data['artifact_sha256'].items():
        assert digest(base/path) == expected
for folder, sha, output in [('flow-config-matrix-c43bfd68e','c43bfd68e31e8c5c98484f954879c5944699a994','comparison-c43bfd68e.json'),('flow-config-matrix-1bc9d1562',FINAL,'comparison-1bc9d1562.json')]:
    result = subprocess.check_output([sys.executable,str(HERE/'verify-comparison.py'),folder,sha],text=True)
    assert json.loads(result) == json.loads((HERE/output).read_text())
print('PASS flow configuration evidence identities, gates, controls and 8/5 differential scope; full SDP acceptance remains open')
