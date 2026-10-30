"""Offline, read-only validation of retained evidence."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'MANIFEST.json').read_text())
expected = {entry['path'] for entry in manifest['files']}
actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
assert actual == expected, (actual - expected, expected - actual)
for entry in manifest['files']:
    data = (root / entry['path']).read_bytes()
    assert len(data) == entry['size'], entry['path']
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
r = json.loads((root / 'results.json').read_text())
assert r['status'] == 'completed' and r['summary'] == {'failed': 0, 'passed': 10}
assert len(r['cases']) == 10 and all(c['status'] == 'passed' and c['events'] for c in r['cases'])
assert r['spark_version'] == r['pyspark_version'] == '4.2.1'
assert r['session_class'] == 'pyspark.sql.connect.session.SparkSession'
assert r['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
assert r['owned_gateway_exit_code'] == 0
assert r['terminal_pid_check']['exit_code'] == 1 and r['terminal_pid_check']['stdout'] == ''
assert r['initial_config']['spark.sql.timeType.enabled'] == 'false'
for c in r['cases']:
    assert c['config']['spark.sql.timeType.enabled'] == 'true'
    assert c['config_after_restore'] == r['initial_config']
    for f in c['created_files']:
        assert hashlib.sha256((root / f['path']).read_bytes()).hexdigest() == f['sha256']
for f in r['source_files']:
    assert hashlib.sha256((root / f['path']).read_bytes()).hexdigest() == f['sha256']
assert hashlib.sha256((root / 'run.py').read_bytes()).hexdigest() == r['run_sha256']
assert hashlib.sha256((root / 'source/sql_helpers.py').read_bytes()).hexdigest() == r['sql_helper']['sha256']
time_case = next(c for c in r['cases'] if c['name'] == 'time_precision')
ns = [col['nanosecond_values'] for e in time_case['events'] if e['operation'] == 'toArrow'
      for col in e['result']['columns'] if 'nanosecond_values' in col]
assert ns == [[0, 45296123456000, 86399999999000, None]] * 4
terminal = json.loads((root / 'terminal-process-check.json').read_text())
assert terminal['exit_code'] == 1 and terminal['stdout'] == '' and terminal['exec_terminal_exit_code'] == 0
print(f'PASS: {len(expected)} retained files; 10 unchanged public Spark Connect cases; raw TIME nanoseconds; cleanup receipts')
