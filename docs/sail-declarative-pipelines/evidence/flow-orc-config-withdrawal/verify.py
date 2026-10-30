from pathlib import Path
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(sys.argv[1])
packet = root / 'docs/sail-declarative-pipelines/evidence/flow-orc-config-withdrawal'
def digest(data):
    return hashlib.sha256(data).hexdigest()
manifest = json.loads((packet / 'provenance.json').read_text())
files = {p.relative_to(packet).as_posix() for p in packet.rglob('*') if p.is_file()}
assert files == {f['path'] for f in manifest['files']} | {'provenance.json'}
for item in manifest['files']:
    data = (packet / item['path']).read_bytes()
    assert len(data) == item['bytes'] and digest(data) == item['sha256'], item['path']
candidate = json.loads((packet / 'candidate.json').read_text())
sail = '/Users/alexy/src/sail-pipelines-proposal'
def git(repo, *args):
    return subprocess.check_output(['git', '-C', repo, *args])
for path in candidate['paths']:
    assert (packet / 'candidate-source' / path).read_bytes() == git(sail, 'show', candidate['commit'] + ':' + path)
assert (packet / 'withdrawn.patch').read_bytes() == git(sail, 'diff', '--binary', candidate['base'], candidate['commit'])
gate = json.loads((packet / 'rust-gate.json').read_text())
assert gate['sail_commit'] == candidate['commit']
assert [(c['name'], c['exit_code']) for c in gate['checks']] == [('fmt', 0), ('clippy', 101)]
for check in gate['checks']:
    assert digest((packet / ('rust-' + check['name'] + '.log')).read_bytes()) == check['sha256']
baseline = json.loads((packet / 'sail-baseline/receipt.json').read_text())
assert baseline['commit'] == candidate['base']
assert baseline['pytest'] == {'tests': 4, 'failures': 2, 'errors': 0, 'skipped': 0}
suite = ET.parse(packet / 'sail-baseline/pytest.xml').getroot().find('testsuite')
assert tuple(int(suite.get(k)) for k in ('tests', 'failures', 'errors', 'skipped')) == (4, 2, 0, 0)
source = packet / 'candidate-source/python/pysail/tests/spark/pipelines/test_flow_file_config.py'
assert digest(source.read_bytes()) == baseline['test_sha256']
reference = json.loads((packet / 'spark-reference/reference.json').read_text())
assert reference['spark_version'] == '4.2.1' and reference['outcome'] == 'failed'
assert reference['test_sha256'] == baseline['test_sha256']
assert [(c['name'], c['outcome']) for c in reference['cases']] == [
    ('graph-default', 'failed'), ('flow-overrides-graph', 'passed'), ('read-option-overrides-flow', 'passed')]
probe = json.loads((packet / 'spark-probe/probe.json').read_text())
assert probe['spark_version'] == '4.2.1' and len(probe['cases']) == 4
for case, graph, flow in zip(probe['cases'][:2], ('true', 'false'), ({}, {'spark.sql.orc.mergeSchema': 'true'})):
    assert case['commands'][0]['sql_conf'] == {'spark.sql.orc.mergeSchema': graph}
    assert next(c for c in case['commands'] if c['kind'] == 'define_flow')['sql_conf'] == flow
    assert case['schema']['fields'] == [{'name': 'id', 'type': 'integer', 'nullable': True, 'metadata': {}}]
    assert case['rows'] == [{'id': i} for i in range(11)]
    assert case['ambient_merge_schema'] == 'false'
assert "struct<id:int>) doesn't match the data schema (struct<id:int,extra:int>)" in probe['cases'][2]['error']
assert set(probe['cases'][3]) == {'name', 'commands'}  # Interrupted: no completed result.
sources = json.loads((packet / 'source-audit/sources.json').read_text())
for entry in sources['sources']:
    repo = sources['repositories'][entry['repository']]['path']
    data = git(repo, 'show', entry['commit'] + ':' + entry['source_path'])
    assert digest(data) == entry['full_source_sha256'] and len(data) == entry['full_source_bytes']
    assert git(repo, 'rev-parse', entry['commit'] + ':' + entry['source_path']).decode().strip() == entry['git_blob_id']
    for window in entry['windows']:
        excerpt = b''.join(data.splitlines(keepends=True)[window['start_line'] - 1:window['end_line']])
        assert excerpt == (packet / 'source-audit' / window['archive_file']).read_bytes()
        assert digest(excerpt) == window['sha256'] and len(excerpt) == window['bytes']
restored = json.loads((packet / 'restoration.json').read_text())
assert restored['sail_head'] == candidate['base'] and not restored['branch_advanced']
assert restored['source_compared_to_candidate_before_restore'] and restored['implementation_worktree_clean']
print('PASS withdrawal evidence: retained failed gates, exact source/candidate hashes, Spark mismatch and incomplete probe')
