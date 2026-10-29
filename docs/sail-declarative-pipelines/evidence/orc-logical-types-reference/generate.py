from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import traceback

ROOT = Path('/tmp/sail-sdp-orc-bridge-reference')
ROOT.mkdir(exist_ok=True)
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
from pyspark.sql import SparkSession
from pyarrow import orc
import pyarrow as pa

s = SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri()).config('spark.sql.session.timeZone', 'UTC').config('spark.sql.timeType.enabled', 'true').getOrCreate()
report = {
    'spark_version': s.version,
    'spark_source_pin': '617618396087429b5627a86ce933bb0f5d6645cb',
    'orc_rust_source_pin': '91910faa90e70587655e40788495a8a936fdf8fe',
    'pyarrow_version': pa.__version__,
    'spark_sql_timeType_enabled': True,
    'initial_default_TIME_attempt': {'outcome': 'failed', 'error': '[UNSUPPORTED_TIME_TYPE] The data type TIME is not supported. SQLSTATE: 0A000', 'log': str(ROOT / 'default-time-disabled.log')},
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'cases': [],
}
if os.environ.get('BRIDGE_RESUME') == '1' and (ROOT / 'expected.json').exists():
    report = json.loads((ROOT / 'expected.json').read_text())

def json_safe(value):
    if isinstance(value, dict):
        if any(not isinstance(key, (str, int, float, bool, type(None))) for key in value):
            return {'__map_entries__': [{'key': json_safe(k), 'value': json_safe(v)} for k,v in value.items()]}
        return {k: json_safe(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value

def save():
    (ROOT / 'expected.json').write_text(json.dumps(json_safe(report), indent=2, default=str) + '\n')

def stage(case, name, fn):
    try:
        value = fn()
        case[name] = {'outcome': 'passed', 'value': value}
        return value
    except Exception as error:
        case[name] = {'outcome': 'failed', 'type': type(error).__name__, 'error': str(error)}
        (ROOT / f"{case['name']}-{name}-failure.txt").write_text(traceback.format_exc())
        return None
    finally:
        save()

def rows(frame):
    return [row.asDict(recursive=True) for row in frame.collect()]

def arrow_info(frame):
    table = frame.toArrow()
    result = {'schema': str(table.schema)}
    # Preserve raw integer values and avoid Python's nanosecond TIME conversion.
    columns = {}
    for field, column in zip(table.schema, table.columns):
        typ = field.type
        if pa.types.is_timestamp(typ) or pa.types.is_time64(typ) or pa.types.is_duration(typ):
            columns[field.name] = {'type': str(typ), 'storage_values': column.cast(pa.int64()).to_pylist()}
        else:
            columns[field.name] = {'type': str(typ), 'values': column.to_pylist()}
    result['columns'] = columns
    return result

def physical_info(path):
    results = []
    for file in sorted(path.glob('*.orc')):
        reader = orc.ORCFile(file)
        table = reader.read()
        integer_storage = {}
        for field, column in zip(table.schema, table.columns):
            if pa.types.is_timestamp(field.type):
                integer_storage[field.name] = column.cast(pa.int64()).to_pylist()
            elif pa.types.is_integer(field.type):
                integer_storage[field.name] = column.to_pylist()
        results.append({'path': str(file), 'compression': reader.compression, 'schema': str(reader.schema), 'rows': table.to_pylist(), 'integer_storage': integer_storage})
    return results

def run(name, query, numeric=None, zone='UTC'):
    prior = next((c for c in report['cases'] if c['name'] == name), None)
    if prior is not None:
        if 'read_arrow' in prior:
            return
        report['cases'].remove(prior)
    case = {'name': name, 'writer': 'Spark 4.2.1', 'sql': query, 'session_timezone': zone}
    report['cases'].append(case)
    s.conf.set('spark.sql.session.timeZone', zone)
    frame = s.sql(query)
    case['source_schema'] = stage(case, 'analysis', lambda: frame.schema.jsonValue())
    if case['source_schema'] is None:
        return
    stage(case, 'source_collect', lambda: rows(frame))
    stage(case, 'source_strings', lambda: rows(frame.selectExpr(*[f'CAST(`{name}` AS STRING) AS `{name}`' for name in frame.columns])))
    if numeric:
        case['numeric_projection_sql'] = numeric
        stage(case, 'source_numeric', lambda: rows(frame.selectExpr(*numeric)))
    stage(case, 'source_arrow', lambda: arrow_info(frame))
    path = ROOT / 'data' / name
    stage(case, 'write', lambda: frame.coalesce(1).write.format('orc').mode('overwrite').save(str(path)))
    case['fixture_directory'] = str(path)
    stage(case, 'physical_arrow', lambda: physical_info(path))
    read = s.read.orc(str(path))
    case['read_schema'] = read.schema.jsonValue()
    stage(case, 'read_collect', lambda: rows(read))
    stage(case, 'read_strings', lambda: rows(read.selectExpr(*[f'CAST(`{name}` AS STRING) AS `{name}`' for name in read.columns])))
    if numeric:
        stage(case, 'read_numeric', lambda: rows(read.selectExpr(*numeric)))
    stage(case, 'read_arrow', lambda: arrow_info(read))
    save()
    print(json.dumps({'case': name, 'stages': {k: v['outcome'] for k, v in case.items() if isinstance(v, dict) and 'outcome' in v}}), flush=True)

try:
    run('time_precisions', '''SELECT id, CAST(t AS TIME(0)) AS t0, CAST(t AS TIME(3)) AS t3, CAST(t AS TIME(6)) AS t6
FROM VALUES (0, '00:00:00'), (1, '12:34:56.123456'), (2, '23:59:59.999999'), (3, CAST(NULL AS STRING)) AS v(id,t)''',
        ['id', 'CAST(t0 AS BIGINT) AS t0_seconds', 'CAST(t3 AS DECIMAL(20,6)) AS t3_seconds', 'CAST(t6 AS DECIMAL(20,6)) AS t6_seconds'])
    run('intervals', '''SELECT id, CAST(ym AS INTERVAL YEAR TO MONTH) AS ym, CAST(y AS INTERVAL YEAR) AS y, CAST(m AS INTERVAL MONTH) AS m,
CAST(dt AS INTERVAL DAY TO SECOND) AS dt, CAST(d AS INTERVAL DAY) AS d, CAST(h AS INTERVAL HOUR) AS h, CAST(mi AS INTERVAL MINUTE) AS mi, CAST(sec AS INTERVAL SECOND) AS sec
FROM VALUES
(0, '1-2', '2', '14', '2 03:04:05.123456', '2', '27', '65', '1.000001'),
(1, '-1-2', '-2', '-14', '-2 03:04:05.123456', '-2', '-27', '-65', '-1.000001'),
(2, '0-0', '0', '0', '0 00:00:00.000000', '0', '0', '0', '0.000001'),
(3, CAST(NULL AS STRING), NULL, NULL, NULL, NULL, NULL, NULL, NULL) AS v(id,ym,y,m,dt,d,h,mi,sec)''',
        ['id'] + [f'CAST(CAST({c} AS INTERVAL YEAR TO MONTH) AS INT) AS {c}_months' for c in ('ym','y','m')] + [f'CAST(CAST(CAST({c} AS INTERVAL DAY TO SECOND) AS DECIMAL(30,6)) * 1000000 AS BIGINT) AS {c}_micros' for c in ('dt','d','h','mi','sec')])
    timestamps = '''SELECT id, CAST(t AS TIMESTAMP_NTZ) AS ntz, CAST(t AS TIMESTAMP_LTZ) AS ltz FROM VALUES
(0, '1969-12-31 23:59:58.123456'), (1, '1969-12-31 23:59:59.000001'), (2, '1969-12-31 23:59:59.999999'),
(3, '1970-01-01 00:00:00'), (4, '2020-01-02 03:04:05.123456'), (5, CAST(NULL AS STRING)) AS v(id,t)'''
    numeric = ['id', 'timestampdiff(MICROSECOND, TIMESTAMP_NTZ\'1970-01-01 00:00:00\', ntz) AS ntz_micros', 'unix_micros(ltz) AS ltz_micros']
    run('timestamps_utc', timestamps, numeric)
    run('timestamps_los_angeles', timestamps, numeric, zone='America/Los_Angeles')
    run('nested_timestamp_nulls', '''SELECT 0 AS id,
named_struct('ntz', TIMESTAMP_NTZ'1969-12-31 23:59:58.123456', 'ltz', TIMESTAMP_LTZ'2020-01-02 03:04:05.123456') AS st,
array(TIMESTAMP_NTZ'1969-12-31 23:59:58.123456', CAST(NULL AS TIMESTAMP_NTZ), TIMESTAMP_NTZ'2020-01-02 03:04:05.123456') AS nts,
array(TIMESTAMP_LTZ'2020-01-02 03:04:05.123456', CAST(NULL AS TIMESTAMP_LTZ)) AS lts,
map('value', TIMESTAMP_NTZ'1969-12-31 23:59:58.123456', 'null', CAST(NULL AS TIMESTAMP_NTZ)) AS ntm,
array(named_struct('ntz', TIMESTAMP_NTZ'2020-01-02 03:04:05.123456', 'ltz', CAST(NULL AS TIMESTAMP_LTZ)), CAST(NULL AS STRUCT<ntz:TIMESTAMP_NTZ,ltz:TIMESTAMP_LTZ>)) AS sts
UNION ALL SELECT 1, CAST(NULL AS STRUCT<ntz:TIMESTAMP_NTZ,ltz:TIMESTAMP_LTZ>), CAST(NULL AS ARRAY<TIMESTAMP_NTZ>), CAST(NULL AS ARRAY<TIMESTAMP_LTZ>), CAST(NULL AS MAP<STRING,TIMESTAMP_NTZ>), CAST(NULL AS ARRAY<STRUCT<ntz:TIMESTAMP_NTZ,ltz:TIMESTAMP_LTZ>>)
UNION ALL SELECT 2, named_struct('ntz', CAST(NULL AS TIMESTAMP_NTZ), 'ltz', CAST(NULL AS TIMESTAMP_LTZ)), array(), array(), map(), array()''')
    run('nested_time_intervals', '''SELECT 0 AS id, array(CAST('12:34:56.123456' AS TIME(6)), CAST(NULL AS TIME(6))) AS times,
named_struct('ym', INTERVAL '-1-2' YEAR TO MONTH, 'dt', INTERVAL '-0 00:00:00.000001' DAY TO SECOND, 't', CAST('01:02:03.123' AS TIME(3))) AS st,
map(INTERVAL '1-2' YEAR TO MONTH, INTERVAL '-1.000001' SECOND) AS intervals
UNION ALL SELECT 1, NULL, NULL, NULL
UNION ALL SELECT 2, array(), named_struct('ym', CAST(NULL AS INTERVAL YEAR TO MONTH), 'dt', CAST(NULL AS INTERVAL DAY TO SECOND), 't', CAST(NULL AS TIME(3))), map()''')
    run('time_cast_precisions', '''SELECT id, CAST(CAST(t AS TIME(6)) AS TIME(0)) AS t0, CAST(CAST(t AS TIME(6)) AS TIME(3)) AS t3, CAST(t AS TIME(6)) AS t6
FROM VALUES (0, '00:00:00'), (1, '12:34:56.123456'), (2, '23:59:59.999999'), (3, CAST(NULL AS STRING)) AS v(id,t)''')
    run('daytime_time_nested', '''SELECT 0 AS id, INTERVAL '-2 03:04:05.123456' DAY TO SECOND AS dt,
array(INTERVAL '-1.000001' SECOND, CAST(NULL AS INTERVAL SECOND), INTERVAL '0.000001' SECOND) AS ds,
map(CAST('01:02:03.123' AS TIME(3)), INTERVAL '-1.000001' SECOND) AS tm,
named_struct('t', CAST('12:34:56.123456' AS TIME(6)), 'd', INTERVAL '-0.000001' SECOND) AS st
UNION ALL SELECT 1, NULL, NULL, NULL, NULL
UNION ALL SELECT 2, INTERVAL '0' DAY, array(), map(), named_struct('t', CAST(NULL AS TIME(6)), 'd', CAST(NULL AS INTERVAL SECOND))''')
    s.conf.set('spark.sql.session.timeZone', 'UTC')
    foreign_path = ROOT / 'data' / 'foreign_char_varchar'
    for timestamp_type in ('TIMESTAMP_LTZ', 'TIMESTAMP_NTZ'):
        name = 'foreign_char_varchar_default_' + timestamp_type.lower()
        if any(c['name'] == name for c in report['cases']):
            continue
        s.conf.set('spark.sql.timestampType', timestamp_type)
        case = {'name': name, 'writer': 'Apache ORC Java from Spark jars; ForeignOrc.java', 'timestamp_type_config': timestamp_type, 'fixture_directory': str(foreign_path)}
        report['cases'].append(case)
        frame = s.read.orc(str(foreign_path))
        case['read_schema'] = frame.schema.jsonValue()
        stage(case, 'read_collect', lambda: rows(frame))
        stage(case, 'read_arrow', lambda: arrow_info(frame))
        stage(case, 'physical_arrow', lambda: physical_info(foreign_path))
finally:
    save()
    s.stop()
