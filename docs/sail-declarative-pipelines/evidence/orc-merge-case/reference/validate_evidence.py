"""Read-only validation of the frozen packet; does not start Spark or write files."""
import hashlib
import json
from pathlib import Path
import pyarrow.orc as orc

ROOT = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def normalized(value):
    return json.loads(json.dumps(value))

def leaf_fields(schema, kind):
    if kind == 'root':
        return schema['fields'][1:]
    field_type = schema['fields'][1]['type']
    if kind == 'list':
        field_type = field_type['elementType']
    elif kind == 'map_value':
        field_type = field_type['valueType']
    return field_type['fields']

def leaf_row(row, kind):
    if kind == 'root':
        return {k: v for k, v in row.items() if k != 'id'}
    if kind == 'struct':
        return row['s']
    if kind == 'list':
        assert len(row['items']) == 1
        return row['items'][0]
    assert len(row['lookup']) == 1 and row['lookup'][0][0] == 'k'
    return row['lookup'][0][1]

manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
for item in manifest['files']:
    data = (ROOT / item['path']).read_bytes()
    assert len(data) == item['size'] and sha(data) == item['sha256'], item['path']
actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
assert actual == {item['path'] for item in manifest['files']}
r = json.loads((ROOT / 'results.json').read_text())
assert r['status'] == 'completed' and r['owned_gateway_exit_code'] == 0
assert r['spark_version'] == '4.2.1' and r['spark_source_pin'] == '617618396087429b5627a86ce933bb0f5d6645cb'
assert r['java']['gateway_pid'] == r['java']['actual_pid'] == 29949
assert r['java']['runtime_version'] == '20.0.2+9-78'
assert r['java']['format_locale'] == 'en-US'
assert r['java']['default_timezone_id'] == r['java']['user_timezone_property'] == 'UTC'
assert r['java']['tzdb_versions'] == ['2023c'] and r['java']['oldmapping_property'] == 'false'
assert r['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
assert not r.get('cleanup_errors') and not r.get('cleanup_termination')
assert r['script_sha256'] == sha((ROOT / 'probe.py').read_bytes())
assert len(r['fixtures']) == 8 and len(r['cases']) == 16 and len(r['merge_diagnostics']) == 8
for name, fixture in r['fixtures'].items():
    path = ROOT / 'inputs' / name
    assert fixture['status'] == 'success' and sha(path.read_bytes()) == fixture['sha256']
    assert path.stat().st_size == fixture['size']
    assert normalized(orc.ORCFile(path).read().to_pylist()) == fixture['input_arrow']['rows'] == fixture['physical_arrow']['rows']
errors = 0
for case in r['cases']:
    sensitive = case['config']['spark.sql.caseSensitive'] == 'true'
    merge = case['reader_options']['mergeSchema'] == 'true'
    kind = case['kind']
    assert case['config']['spark.sql.orc.impl'] == 'native'
    assert case['config']['spark.sql.orc.enableVectorizedReader'] == 'true'
    assert case['config']['spark.sql.orc.enableNestedColumnVectorizedReader'] == 'true'
    if not sensitive and merge and kind != 'root':
        assert case['status'] == 'error' and case['stage'] == 'read_schema'
        assert case['error']['condition'] == 'COLUMN_ALREADY_EXISTS'
        assert case['error']['traceback'] and case['error']['message']
        assert 'read_schema' not in case and 'arrow' not in case
        errors += 1
        continue
    assert case['status'] == 'success' and case['arrow']['num_rows'] == 2
    assert case['read_schema'] == case['output_schema']
    assert 'Scan orc' in case['physical_plan']
    names = ['value', 'Value'] if sensitive and merge else ['value']
    assert [f['name'] for f in leaf_fields(case['read_schema'], kind)] == names
    assert all(f['nullable'] and f['type'] == 'integer' and f['metadata'] == {} for f in leaf_fields(case['read_schema'], kind))
    rows = {row['id']: leaf_row(row, kind) for row in case['arrow']['rows']}
    assert set(rows) == {11, 22}
    expected_lower = {'value': 222}
    expected_upper = {'value': None if sensitive else 111}
    if sensitive and merge:
        expected_lower['Value'] = None
        expected_upper['Value'] = 111
    assert rows == {11: expected_upper, 22: expected_lower}, case['name']
assert errors == 3
for diagnostic in r['merge_diagnostics']:
    assert diagnostic['status'] == 'success'
    names = ['Value'] if diagnostic['kind'] == 'root' and not diagnostic['case_sensitive_argument'] else ['Value', 'value']
    assert [f['name'] for f in leaf_fields(diagnostic['merged_schema'], diagnostic['kind'])] == names
for source in json.loads((ROOT / 'source-audit.json').read_text())['sources']:
    data = (ROOT / source['file']).read_bytes()
    assert sha(data) == source['sha256']
    for excerpt in source['excerpts']:
        expected = b''.join(data.splitlines(keepends=True)[excerpt['first_line']-1:excerpt['last_line']])
        assert (ROOT / excerpt['file']).read_bytes() == expected
        assert sha(expected) == excerpt['sha256']
summary = json.loads((ROOT / 'summary.json').read_text())
assert summary['harness_exit_code'] == 0
assert summary['owned_gateway_absence_check']['exit_code'] == 1
assert summary['owned_gateway_absence_check']['stdout'] == ''
print(json.dumps({'status': 'pass', 'fixtures': 8, 'file_read_cases': 16, 'successful_reads': 13, 'retained_schema_errors': 3, 'direct_merge_diagnostics': 8, 'manifest_sha256': sha((ROOT / 'MANIFEST.json').read_bytes())}, sort_keys=True))
