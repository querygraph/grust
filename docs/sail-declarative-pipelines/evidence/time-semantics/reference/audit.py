"""Read retained oracle output, pair source, and verify acceptance observations. No Spark run."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
r = json.loads((ROOT / 'results.json').read_text())

def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})

def digest(data):
    return hashlib.sha256(data).hexdigest()

supplement = []
for name, path, first, last in (
    ('cast-identity-interpreted', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', 1268, 1286),
    ('parser-default', 'sql/api/src/main/scala/org/apache/spark/sql/catalyst/parser/DataTypeAstBuilder.scala', 352, 364),
    ('config-gate', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/util/TypeUtils.scala', 137, 148),
):
    data = git('show', f'{PIN}:{path}')
    excerpt = b''.join(data.splitlines(keepends=True)[first - 1:last])
    output = 'source-' + name + '.txt'
    (ROOT / output).write_bytes(excerpt)
    supplement.append({'name': name, 'path': path, 'first_line': first, 'last_line': last,
                       'git_blob': git('rev-parse', f'{PIN}:{path}').decode().strip(),
                       'source_sha256': digest(data), 'excerpt': output,
                       'excerpt_sha256': digest(excerpt)})
(ROOT / 'source-supplement.json').write_text(json.dumps({'source_pin': PIN, 'sources': supplement}, indent=2) + '\n')

checks = []
def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    assert condition, name

cases = {c['name']: c for c in r['cases']}
check('bounded runtime and exact version', r['completed'] and r['master'] == 'local[1]' and r['spark_version'] == '4.2.1')
check('normal default false and explicit true', r['config_initial']['spark.sql.timeType.enabled'] == 'false' and r['config_enabled'] == 'true')
expected_failures = {
    'default_config_typed_null': 'UNSUPPORTED_TIME_TYPE',
    'explicit_disabled_typed_null': 'UNSUPPORTED_TIME_TYPE',
    'unsupported_precision_7': 'UNSUPPORTED_TIME_PRECISION',
    'unsupported_precision_9': 'UNSUPPORTED_TIME_PRECISION',
    **{name: 'CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE' for name in (
        'merge_p0_p3', 'merge_p3_p6', 'merge_p6_p3', 'merge_p1_p2', 'merge_time_and_null',
        'merge_nested_array_mismatch', 'merge_nested_struct_mismatch', 'merge_nested_map_mismatch')},
}
for name, case in cases.items():
    if name in expected_failures:
        error = case.get('error', {})
        condition = error.get('getCondition', error.get('java_getCondition'))
        check(name + ' retained expected rejection', case['outcome'] == 'failed' and condition == expected_failures[name])
        check(name + ' traceback retained', (ROOT / error['traceback']).is_file())
    else:
        check(name + ' completed successfully', case['outcome'] == 'passed')

nulls = cases['typed_null_all_precisions']['value']
check('typed null precision schema', [x['type'] for x in nulls['schema']['fields']] == [f'time({p})' for p in range(7)] + ['time(6)'])
check('typed null values', all(x['nanoseconds'] == [None] and x['nullable'] for x in nulls['columns']))
for c in cases.values():
    for column in c.get('value', {}).get('columns', []):
        check(c['name'] + '/' + column['name'] + ' nanosecond Arrow storage', column['arrow_type'] == 'time64[ns]')

nanos = 45296123456000
for kind in ('constant', 'dynamic'):
    check('string casts preserve full input ' + kind, all(x['nanoseconds'] == [nanos]
          for x in cases['string_cast_all_precisions_' + kind]['value']['columns']))
    columns = cases['cross_precision_matrix_' + kind]['value']['columns']
    expected = [nanos if a == b else (nanos // 10 ** (9 - b)) * 10 ** (9 - b)
                for a in range(7) for b in range(7)]
    check('cross precision matrix identity/truncation ' + kind,
          [x['nanoseconds'][0] for x in columns] == expected)
check('narrow then widen retains narrowed value',
      [x['nanoseconds'][0] for x in cases['narrow_then_widen']['value']['columns']] ==
      [(nanos // 10 ** (9 - p)) * 10 ** (9 - p) for p in range(6)])
check('null and midnight/day-end preserve bits', cases['null_and_day_boundaries']['value']['columns'][0]['nanoseconds'] == [0, 86399999999000, None])
for p in (0, 3, 6):
    fields = cases[f'merge_p{p}_p{p}']['value']['schema']['fields']
    check('same precision nullable merge ' + str(p), fields == [{'name': 't', 'type': f'time({p})', 'nullable': True, 'metadata': {}}])
check('distinct names retained without precision unification',
      [f['type'] for f in cases['merge_distinct_field_names']['value']['schema']['fields']] == ['time(0)', 'time(6)'])
for s in r['source_evidence'] + supplement:
    data = git('show', f"{PIN}:{s['path']}")
    excerpt = b''.join(data.splitlines(keepends=True)[s['first_line'] - 1:s['last_line']])
    check(s['name'] + ' source matches pin', digest(data) == s['source_sha256'] and
          excerpt == (ROOT / s['excerpt']).read_bytes() and digest(excerpt) == s['excerpt_sha256'])
validation = {'created_at': datetime.now(timezone.utc).isoformat(), 'runtime_runs_in_this_audit': 0,
              'source_pin': PIN, 'source_excerpts': len(r['source_evidence']) + len(supplement),
              'cases': len(cases), 'successful_cases': len(cases) - len(expected_failures),
              'retained_expected_rejections': len(expected_failures), 'checks': checks}
(ROOT / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
print(json.dumps({k: v for k, v in validation.items() if k != 'checks'}))
print('checks:', len(checks), 'all passed')
