"""Offline validation/source capture; never runs Spark or rewrites fixtures."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, value): (ROOT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
def columns(case): return {c['name']: c['values'] for c in case['arrow']['columns']}
def git(*args): return subprocess.check_output(['git', '-C', str(SPARK), *args])

anchors = [
    ('orc-utils', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala', [(135, 178), (193, 303), (316, 349)]),
    ('orc-reader', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcFileFormat.scala', [(175, 245)]),
    ('orc-deserializer', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcDeserializer.scala', [(108, 131), (158, 209)]),
    ('orc-vector', 'sql/core/src/main/java/org/apache/spark/sql/execution/datasources/orc/OrcAtomicColumnVector.java', [(79, 112)]),
    ('sql-casts', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', [(828, 879), (1497, 1528)]),
    ('schema-merge', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/SchemaMergeUtils.scala', [(35, 119)]),
    ('struct-merge', 'sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala', [(597, 707)]),
    ('time-config', 'sql/catalyst/src/main/scala/org/apache/spark/sql/internal/SQLConf.scala', [(7435, 7442)]),
]
sources = []
for label, path, ranges in anchors:
    raw = git('show', f'{PIN}:{path}')
    lines = raw.splitlines(keepends=True)
    entry = {'path': path, 'commit': PIN, 'git_blob': git('rev-parse', f'{PIN}:{path}').decode().strip(),
             'source_sha256': hashlib.sha256(raw).hexdigest(), 'excerpts': []}
    for first, last in ranges:
        assert 1 <= first <= last <= len(lines)
        target = Path('sources') / f'{label}-{first}-{last}.txt'
        (ROOT / target).parent.mkdir(exist_ok=True)
        (ROOT / target).write_bytes(b''.join(lines[first - 1:last]))
        entry['excerpts'].append({'first_line': first, 'last_line': last, 'file': str(target), 'sha256': sha(ROOT / target)})
    sources.append(entry)
save('source-audit.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'repository': str(SPARK), 'commit': PIN, 'sources': sources})

r = json.loads((ROOT / 'results.json').read_text())
assert r['status'] == 'completed' and r['owned_gateway_exit_code'] == 0
assert r['spark_version'] == '4.2.1' and r['time_enabled_before_override'] == 'false'
assert len(r['cases']) == len(r['case_plan']) == 28
assert sha(ROOT / 'probe.py') == r['script_sha256']
cases = {c['name']: c for c in r['cases']}
assert len(cases) == 28
assert Counter(c['status'] for c in cases.values()) == {'success': 25, 'error': 3}
for c in cases.values():
    assert c['config']['spark.sql.timeType.enabled'] == 'true'
    assert c['config']['spark.sql.ansi.enabled'] == 'true'
    if c['status'] == 'success':
        assert c['stage'] == 'materialize_to_arrow'
        assert c['physical_plan'] and c['read_schema'] and c['output_schema']
        planned_batched = c['config']['spark.sql.orc.enableVectorizedReader']
        assert f'Batched: {planned_batched}' in c['physical_plan']
for f in r['fixtures'].values():
    path = ROOT / Path(f['path']).relative_to(Path(r['fixtures']['time_precisions']['path']).parents[1])
    assert sha(path) == f['sha256']
    if f.get('source', {}).get('original_sha256'):
        assert f['sha256'] == f['source']['original_sha256']
for members in r['multi_file_inputs'].values():
    assert len(members) == 11
    for item in members:
        path = ROOT / 'multi' / Path(item['file']).parent.name / Path(item['file']).name
        assert sha(path) == item['sha256'] == r['fixtures'][item['source_fixture']]['sha256']

raw_time = [0, 45296123456000, 86399999999000, None]
for name, c in cases.items():
    if name.startswith('time0_') and name != 'time0_sql_cast_controls':
        assert columns(c) == {'id': [0, 1, 2, 3], 't0': raw_time, 't3': raw_time, 't6': raw_time}
        if 'requested_p' in name:
            precision = int(name.split('requested_p')[1][0])
            assert c['read_schema']['fields'][1]['type'] == f'time({precision})'
assert columns(cases['time0_sql_cast_controls']) == {'id': [0, 1, 2, 3], 'p3': [0, 45296123000000, 86399999000000, None], 'p6': raw_time}
physical_intervals = {c['name']: c['values'] for c in r['fixtures']['intervals']['physical_arrow']['columns']}
interval_expected = {('id' if n == 'id' else n + ('_months' if n in ['ym', 'y', 'm'] else '_micros')): v for n, v in physical_intervals.items()}
for name, c in cases.items():
    if name.startswith('interval_'):
        assert columns(c) == interval_expected
        fields = {f['name']: f['type'] for f in c['read_schema']['fields']}
        if 'narrow_ym' in name: assert fields['ym'] == 'interval year'
        if 'narrow_dt' in name: assert fields['dt'] == 'interval day'
        if name == 'interval_widen_qualifiers':
            assert fields['y'] == 'interval year to month' and fields['d'] == 'interval day to second'
raw_i = [-129, -128, 127, 128, 32768, None]
raw_b = [-2147483649, -2147483648, 2147483647, 2147483648, 128, None]
for name, c in cases.items():
    if name.startswith('integer_'):
        expected = {'id': list(range(6)), 'i': raw_i, 'b': raw_b}
        if 'requested_b_int' in name: expected['b'] = [None, -2147483648, 2147483647, None, 128, None]
        if name == 'integer_int_to_byte_boundaries': expected['i'] = [None, -128, 127, None, None, None]
        assert columns(c) == expected
assert columns(cases['mixed_nested_case_sensitive_True']) == {'foo': [None, None], 'ST': [None, None]}
assert columns(cases['mixed_nested_case_sensitive_False']) == {'foo': [11, None], 'ST': [{'bar': 22}, None]}
assert columns(cases['top_and_nested_missing_fields']) == {'Foo': [11, None], 'st': [{'Bar': 22, 'absent': None}, None], 'absent': [None, None]}
assert columns(cases['ambiguous_nested_case_insensitive']) == {'st': [{'bar': 22}]}
error = cases['ambiguous_top_case_insensitive']
assert error['stage'] == 'materialize_to_arrow' and error['error']['condition'] == 'FAILED_READ_FILE.NO_HINT'
assert 'Found duplicate field(s)' in error['error']['message']
assert columns(cases['eleventh_field_merge_false']) == {'t': [45296123456000] * 11}
merged = columns(cases['eleventh_field_merge_true'])
assert merged['t'] == [45296123456000] * 11
assert Counter(merged['eleventh']) == {None: 10, 11: 1}
union = cases['eleventh_interval_qualifier_union']
assert [f['type'] for f in union['read_schema']['fields']] == ['interval year to month', 'interval day to second']
assert Counter(zip(*columns(union).values())) == {(24, 259200000000): 10, (14, 1000001): 1}
for name in ['eleventh_time_precision_conflict', 'eleventh_interval_family_conflict']:
    assert cases[name]['stage'] == 'schema' and cases[name]['error']['condition'] == 'CANNOT_MERGE_SCHEMAS'
assert columns(cases['hive_fallback_renamed_fields']) == {'first': [11, None], 'second': ['eleven', None]}
assert columns(cases['hive_fallback_project_second']) == {'second': ['eleven', None]}
summary = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Observed Spark only, no Sail runtime qualification or selected production policy',
           'source_pin': PIN, 'cases_total': 28, 'successful_reads': 25, 'errors': 3, 'harness_attempts': 1,
           'time_enabled_default': r['time_enabled_before_override'], 'time_enabled_during_cases': 'true',
           'owned_gateway_pid': r['java']['gateway_pid'], 'owned_gateway_exit_code': r['owned_gateway_exit_code'],
           'exact_values_and_schemas_offline_validated': True,
           'cases': [{'name': c['name'], 'status': c['status'], 'stage': c['stage'], 'condition': c.get('error', {}).get('condition'),
                      'vectorized_setting': c['config']['spark.sql.orc.enableVectorizedReader'],
                      'case_sensitive_setting': c['config']['spark.sql.caseSensitive']} for c in r['cases']]}
save('summary.json', summary)
files, excluded = [], []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or path.name == 'MANIFEST.json': continue
    relative = path.relative_to(ROOT)
    entry = {'file': str(relative), 'sha256': sha(path), 'size': path.stat().st_size}
    if path.suffix == '.crc' or path.name == '_SUCCESS' or relative.parts[0] in ['spark-local', 'warehouse']:
        excluded.append({**entry, 'reason': 'Generated Hadoop bookkeeping/runtime state; not used as evidence'})
    else: files.append(entry)
save('MANIFEST.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'original_root': str(ROOT),
                      'portable_mapping': 'Relative file paths map original root to archive; raw absolute receipt paths preserved',
                      'files': files, 'excluded': excluded, 'excluded_directory_rules': ['spark-local/**', 'warehouse/**']})
print('Validated 28 observations, all 25 successful value/schema sets, 57 ORC file hashes, 1 clean owned JVM;', len(files), 'retained files')
