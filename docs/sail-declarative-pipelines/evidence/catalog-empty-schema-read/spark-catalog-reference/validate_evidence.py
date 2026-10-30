"""Offline read-only validation; does not start Spark or alter retained evidence."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'MANIFEST.json').read_text())
actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
assert actual == {f['path'] for f in manifest['files']}
for entry in manifest['files']:
    data = (root / entry['path']).read_bytes()
    assert len(data) == entry['size'] and hashlib.sha256(data).hexdigest() == entry['sha256']
r = json.loads((root / 'results.json').read_text())
assert r['status'] == 'completed' and r['summary'] == {'succeeded': 7, 'error': 0}
assert r['spark_version'] == r['pyspark_version'] == '4.2.1'
assert r['session_class'] == 'pyspark.sql.connect.session.SparkSession'
assert r['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
assert r['java']['version'] == '20.0.2+9-78' and r['java']['default_timezone'] == 'UTC'
assert r['all_input_files_unchanged'] and r['inputs_before'] == r['inputs_after']
for entry in r['inputs_before']:
    data = (root / entry['path']).read_bytes()
    assert len(data) == entry['size'] and hashlib.sha256(data).hexdigest() == entry['sha256']
assert len(r['cases']) == 7
assert {(c['format'], c['explicit_schema']) for c in r['cases'][:6]} == {(fmt, flag) for fmt in ['orc', 'parquet', 'json'] for flag in [False, True]}
for case in r['cases'][:6]:
    assert case['status'] == 'succeeded' and case['file_unchanged']
    assert case['table_rows'] == case['direct_rows'] == [[3], [1]]
    expected = 'long' if case['format'] == 'json' and not case['explicit_schema'] else 'integer'
    assert case['table_schema'] == {'type': 'struct', 'fields': [{'name': 'id', 'type': expected, 'nullable': True, 'metadata': {}}]}
    assert case['describe'][0] == ['id', 'bigint' if expected == 'long' else 'int', None]
case = r['cases'][-1]
assert case['status'] == 'succeeded' and case['existing_table_unchanged']
assert case['missing_path_before'] is case['missing_path_after'] is False
assert case['missing_new_table_control']['outcome'] == 'error'
assert case['missing_new_table_control']['error']['condition'] == 'UNABLE_TO_INFER_SCHEMA'
assert case['control_table_exists'] is False
assert r['owned_gateway_exit_code'] == 0 and r['terminal_pid_check']['exit_code'] == 1 and not r['terminal_pid_check']['stdout']
assert hashlib.sha256((root / 'run.py').read_bytes()).hexdigest() == r['script_sha256']
assert hashlib.sha256((root / 'source/sail-catalog-control.py').read_bytes()).hexdigest() == r['original_control']['sha256']
assert hashlib.sha256((root / 'source/createDataSourceTables.scala').read_bytes()).hexdigest() == r['source_anchor']['sha256']
t = json.loads((root / 'terminal-process-check.json').read_text())
assert t['exit_code'] == 1 and not t['stdout'] and t['exec_terminal_exit_code'] == 0
print(f'PASS: {len(actual)} files; six catalog schema observations; existing-table guard plus retained negative control; exact inputs and cleanup receipts')
