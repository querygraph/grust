"""Read-only offline validation of the retained four Spark observations."""
import hashlib
import json
from pathlib import Path
import subprocess

import pyarrow.orc as orc

ROOT = Path(__file__).resolve().parent
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
for item in manifest['files']:
    data = (ROOT / item['path']).read_bytes()
    assert len(data) == item['size'] and sha(data) == item['sha256'], item['path']
results = json.loads((ROOT / 'results.json').read_text())
summary = json.loads((ROOT / 'summary.json').read_text())
assert results['status'] == 'completed' and results['spark_version'] == '4.2.1'
assert results['spark_source_pin'] == PIN
assert results['script_sha256'] == sha((ROOT / 'probe.py').read_bytes())
assert results['owned_gateway_exit_code'] == 0
assert results['java']['gateway_pid'] == results['java']['actual_pid'] == 5469
assert results['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
assert summary['owned_gateway_absence_check']['exit_code'] == 1
assert not summary['owned_gateway_absence_check']['stdout']
assert len(results['cases']) == 4 and len(results['fixtures']) == 2
for fixture in results['fixtures'].values():
    assert fixture['status'] == 'success'
    path = ROOT / 'inputs' / Path(fixture['path']).name
    assert sha(path.read_bytes()) == fixture['sha256']
duplicate = orc.ORCFile(ROOT / 'inputs/duplicate_exact_top.orc').read()
assert duplicate.column_names == ['dup', 'dup']
assert [duplicate.column(i).to_pylist() for i in range(2)] == [[11], [22]]
map_table = orc.ORCFile(ROOT / 'inputs/map_long_keys.orc').read()
assert map_table.column(0).to_pylist() == [[(1, 'one'), (2147483648, 'overflow')]]
cases = {case['name']: case for case in results['cases']}
exact = cases['duplicate_sensitive_true']
assert exact['status'] == 'success' and exact['arrow']['columns'][0]['values'] == [22]
insensitive = cases['duplicate_sensitive_false']
assert insensitive['status'] == 'error'
assert insensitive['stage'] == 'materialize_to_arrow'
assert 'Found duplicate field(s)' in insensitive['error']['message']
vector = cases['map_key_narrow_vector_true']
assert vector['status'] == 'success'
assert [c['values'] for c in vector['arrow']['columns']] == [[1, -2147483648], ['one', 'overflow']]
row = cases['map_key_narrow_vector_false']
assert row['status'] == 'error' and row['stage'] == 'materialize_to_arrow'
assert row['error']['condition'] == 'FAILED_READ_FILE.NO_HINT'
assert 'Batched: true' in vector['physical_plan'] and 'Batched: false' in row['physical_plan']
assert vector['projection'] == row['projection'] == 'explode(m) AS (key, value)'
log = (ROOT / 'probe.log').read_text()
assert 'Caused by: java.lang.NullPointerException' in log
assert 'org.apache.orc.mapred.OrcMapredRecordReader.nextMap' in log
assert 'java.util.TreeMap.put' in log
for case in results['cases']:
    assert case['config']['spark.sql.ansi.enabled'] == 'true'
    assert case['config']['spark.sql.timeType.enabled'] == 'false'
    assert case['config']['spark.sql.session.timeZone'] == 'UTC'
    assert case['read_schema'] == case['requested_schema']
audit = json.loads((ROOT / 'source-audit.json').read_text())
assert audit['commit'] == PIN
for source in audit['sources']:
    data = (ROOT / source['file']).read_bytes()
    assert sha(data) == source['sha256']
    original = subprocess.check_output(['git', 'show', f'{PIN}:{source["path"]}'], cwd=audit['repository'])
    assert data == original
    excerpt = source['excerpt']
    expected = b''.join(data.splitlines(keepends=True)[excerpt['first_line']-1:excerpt['last_line']])
    assert (ROOT / excerpt['file']).read_bytes() == expected
    assert sha(expected) == excerpt['sha256']
for artifact in audit['compiled_artifacts']:
    assert sha((ROOT / artifact['file']).read_bytes()) == artifact['class_sha256']
    output = subprocess.check_output([
        '/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home/bin/javap',
        '-classpath', str(ROOT / 'bytecode/classes'), '-p', '-c', artifact['class']])
    assert output == (ROOT / artifact['disassembly']).read_bytes()
    assert sha(output) == artifact['disassembly_sha256']
print('PASS: 4 retained Spark observations, 2 physical fixtures, 5 pinned sources, 3 compiled classes; no Spark execution')
