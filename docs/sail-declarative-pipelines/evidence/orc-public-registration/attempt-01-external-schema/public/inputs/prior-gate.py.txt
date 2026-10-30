from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET

root = Path('/Users/alexy/src/sail-sdp-gate')
output = Path('/tmp/sail-sdp-time-public')
python = '/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
candidate = json.loads(Path('/tmp/sail-sdp-time-public-candidate.json').read_text())
def git(*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD') == candidate['commit']
assert not git('status','--porcelain')
assert subprocess.run(['git','-C',str(root),'symbolic-ref','-q','HEAD'],capture_output=True).returncode == 1
source = root / candidate['paths'][0]
assert source.read_bytes() == (output/'test_time_precision.py').read_bytes()
base = Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/8d044db3860b4f55e49543c833246af31e986e2e/pytest.xml')
nodes = [t.get('classname').replace('.','/')+'.py::'+t.get('name') for t in ET.parse(base).iter('testcase')]
assert len(nodes) == len(set(nodes)) == 277
nodes.append(candidate['paths'][0])
(output/'selected-nodes.json').write_text(json.dumps(nodes,indent=2)+'\n')
receipt = {'sail_commit':candidate['commit'], 'base':candidate['base'], 'recorded_at':datetime.now(timezone.utc).isoformat(),
           'cli_sha256':json.loads((output/'build.json').read_text())['cli_sha256'],
           'test_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
           'scope':'285 selected public pytest cases plus67 selected upstream Python executions; not full SDP qualification.',
           'server_environment': {'PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages', 'VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv'},
           'checks':[]}
ruff = '/Users/alexy/.cache/uv/archive-v0/Mi-CiNT8OaLEq_dG/ruff-0.16.9.data/scripts/ruff'
commands = [
    ('ruff',[ruff,'check',candidate['paths'][0]]),
    ('ruff-format',[ruff,'format','--check',candidate['paths'][0]]),
    ('pytest',[python,'-m','pytest','-q',*nodes,'--junitxml='+str(output/'pytest.xml')]),
    ('upstream',[python,'scripts/spark-pipelines-tests/run.py','--spark-source','/Users/alexy/src/spark-sdp-4.2.1','--remote','sc://localhost:50086','--report',str(output/'upstream.json')]),
]
for name, command in commands:
    with (output/(name+'.log')).open('w') as log:
        result = subprocess.run(command,cwd=root,env={**os.environ,'PYTHONPATH':'python','SPARK_REMOTE':'sc://localhost:50086'},stdout=log,stderr=subprocess.STDOUT)
    receipt['checks'].append({'name':name,'exit_code':result.returncode,'command':command,
                             'log_sha256':hashlib.sha256((output/(name+'.log')).read_bytes()).hexdigest()})
    (output/'gate.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if result.returncode:
        print((output/(name+'.log')).read_text()[-18000:],flush=True)
        raise SystemExit(result.returncode)
    assert git('rev-parse','HEAD') == candidate['commit'] and not git('status','--porcelain')
    print('PASS TIME public '+name,flush=True)
suite = ET.parse(output/'pytest.xml').getroot().find('testsuite')
assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped')) == ('285','0','0','0')
upstream = json.loads((output/'upstream.json').read_text())
assert upstream['tests_run'] == 67 and upstream['server_spark_version'] == '4.2.1'
assert upstream['failures'] == upstream['errors'] == upstream['skipped'] == 0
reference = json.loads((output/'spark/results.json').read_text())
assert reference['server_spark_version'] == '4.2.1' and len(reference['cases']) == 8
assert all(case['outcome'] == 'passed' for case in reference['cases'])
assert reference['test_source_sha256'] == receipt['test_source_sha256']
assert git('rev-parse','HEAD') == candidate['commit'] and not git('status','--porcelain')
receipt['outcome'] = 'passed'
receipt['completed_at'] = datetime.now(timezone.utc).isoformat()
(output/'gate.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS detached public gate '+candidate['commit'],flush=True)
