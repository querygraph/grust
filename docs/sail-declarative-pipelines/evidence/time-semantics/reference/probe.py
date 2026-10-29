"""Bounded, standalone Spark TIME schema/value oracle; no Sail runtime involved."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
SPARK_REPO = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
import pyarrow as pa
import pyspark
from pyspark.sql import SparkSession

report = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'source_pin': PIN,
    'python': sys.executable,
    'pyspark_version': pyspark.__version__,
    'pyspark_path': pyspark.__file__,
    'pyarrow_version': pa.__version__,
    'runtime_qualification': 'Installed Spark only; no Sail execution or qualification.',
    'runtime_identity_limit': 'Runtime Spark version and jar hashes recorded; installed artifacts are not asserted to have been built from the source pin.',
    'source_evidence': [],
    'cases': [],
}

def save():
    (ROOT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')

def exception(error, filename):
    value = {'python_type': type(error).__name__, 'message': str(error)}
    for name in ('getCondition', 'getSqlState', 'getMessageParameters'):
        try:
            result = getattr(error, name)()
            value[name] = dict(result) if name == 'getMessageParameters' else result
        except Exception:
            pass
    java_error = getattr(error, 'java_exception', None)
    if java_error is not None:
        value['java_class'] = str(java_error.getClass().getName())
        for name in ('getCondition', 'getSqlState', 'getMessageParameters'):
            try:
                result = getattr(java_error, name)()
                value['java_' + name] = dict(result) if name == 'getMessageParameters' else result
            except Exception:
                pass
    (ROOT / filename).write_text(traceback.format_exc())
    value['traceback'] = filename
    return value

def case(name, action, **context):
    entry = {'name': name, **context}
    report['cases'].append(entry)
    try:
        entry['value'] = action()
        entry['outcome'] = 'passed'
    except Exception as error:
        entry['outcome'] = 'failed'
        entry['error'] = exception(error, name + '.failure.txt')
    finally:
        save()
    return entry

def git(*args):
    return subprocess.check_output(['git', '-C', str(SPARK_REPO), *args])

def source(name, path, first, last):
    data = git('show', f'{PIN}:{path}')
    lines = data.decode().splitlines(keepends=True)
    excerpt = ''.join(lines[first - 1:last]).encode()
    output = 'source-' + name + '.txt'
    (ROOT / output).write_bytes(excerpt)
    report['source_evidence'].append({
        'name': name, 'path': path, 'first_line': first, 'last_line': last,
        'git_blob': git('rev-parse', f'{PIN}:{path}').decode().strip(),
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'excerpt': output, 'excerpt_sha256': hashlib.sha256(excerpt).hexdigest(),
    })

source('time-type', 'sql/api/src/main/scala/org/apache/spark/sql/types/TimeType.scala', 23, 59)
source('config', 'sql/catalyst/src/main/scala/org/apache/spark/sql/internal/SQLConf.scala', 7435, 7442)
source('arrow-type', 'sql/api/src/main/scala/org/apache/spark/sql/util/ArrowUtils.scala', 64, 75)
source('cast-interpreted', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', 828, 837)
source('cast-codegen', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', 1497, 1529)
source('cast-same-structure', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', 1348, 1373)
source('truncate', 'sql/api/src/main/scala/org/apache/spark/sql/catalyst/util/SparkDateTimeUtils.scala', 158, 185)
source('string-parser', 'sql/api/src/main/scala/org/apache/spark/sql/catalyst/util/SparkDateTimeUtils.scala', 711, 786)
source('merge-entry', 'sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala', 477, 488)
source('merge-struct', 'sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala', 597, 641)
source('merge-types', 'sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala', 643, 701)
jar_dir = Path(pyspark.__file__).parent / 'jars'
report['runtime_jar_identity'] = [
    {'name': path.name, 'bytes': path.stat().st_size,
     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for pattern in ('spark-sql-api_*.jar', 'spark-catalyst_*.jar', 'spark-sql_*.jar')
    for path in sorted(jar_dir.glob(pattern))
]
save()

spark = None
try:
    spark = (SparkSession.builder.master('local[1]').appName('sail-time-semantic-reference')
             .config('spark.ui.enabled', 'false')
             .config('spark.driver.memory', '512m')
             .config('spark.executor.memory', '512m')
             .config('spark.sql.shuffle.partitions', '1')
             .config('spark.default.parallelism', '1')
             .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri())
             .config('spark.sql.session.timeZone', 'UTC')
             .getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    report['spark_version'] = spark.version
    report['master'] = spark.sparkContext.master
    report['session_class'] = str(type(spark))
    report['config_initial'] = {key: spark.conf.get(key) for key in (
        'spark.sql.timeType.enabled', 'spark.sql.session.timeZone', 'spark.sql.ansi.enabled',
        'spark.sql.codegen.wholeStage', 'spark.sql.shuffle.partitions')}
    report['spark_testing_property'] = spark.sparkContext._jvm.java.lang.System.getProperty('spark.testing')
    if spark.version != '4.2.1':
        raise RuntimeError('Unexpected Spark version: ' + spark.version)

    def sql_result(query):
        frame = spark.sql(query)
        schema_json = json.loads(frame._jdf.schema().json())
        # Record the schema before Arrow export; an export failure does not erase analysis evidence.
        report['cases'][-1]['analyzed_schema'] = schema_json
        report['cases'][-1]['analyzed_schema_ddl'] = frame._jdf.schema().toDDL()
        save()
        table = frame.toArrow()
        columns = []
        for field, column in zip(table.schema, table.columns):
            columns.append({'name': field.name, 'arrow_type': str(field.type),
                            'nullable': field.nullable,
                            'nanoseconds': column.cast(pa.int64()).to_pylist()})
        return {'schema': schema_json, 'arrow_schema': str(table.schema),
                'rows': table.num_rows, 'columns': columns,
                'optimized_plan': frame._jdf.queryExecution().optimizedPlan().toString()}

    def sql_case(name, query):
        return case(name, lambda: sql_result(query), sql=query,
                    time_enabled=spark.conf.get('spark.sql.timeType.enabled'))

    sql_case('default_config_typed_null', 'SELECT CAST(NULL AS TIME) AS t')
    spark.conf.set('spark.sql.timeType.enabled', 'false')
    sql_case('explicit_disabled_typed_null', 'SELECT CAST(NULL AS TIME(3)) AS t')
    spark.conf.set('spark.sql.timeType.enabled', 'true')
    report['config_enabled'] = spark.conf.get('spark.sql.timeType.enabled')
    sql_case('typed_null_all_precisions', 'SELECT ' + ', '.join(
        [f'CAST(NULL AS TIME({p})) AS t{p}' for p in range(7)] + ['CAST(NULL AS TIME) AS t_default']))
    for p in (7, 9):
        sql_case(f'unsupported_precision_{p}', f'SELECT CAST(NULL AS TIME({p})) AS t')

    literal = "'12:34:56.123456'"
    sql_case('string_cast_all_precisions_constant', 'SELECT ' + ', '.join(
        [f'CAST({literal} AS TIME({p})) AS t{p}' for p in range(7)] + [f'CAST({literal} AS TIME) AS t_default']))
    dynamic_input = "FROM (SELECT concat('12:34:56.', cast(id AS STRING)) AS s FROM range(123456, 123457))"
    sql_case('string_cast_all_precisions_dynamic', 'SELECT ' + ', '.join(
        f'CAST(s AS TIME({p})) AS t{p}' for p in range(7)) + ' ' + dynamic_input)
    for kind, expression, suffix in (
        ('constant', literal, ''), ('dynamic', 's', ' ' + dynamic_input)
    ):
        sql_case('cross_precision_matrix_' + kind, 'SELECT ' + ', '.join(
            f'CAST(CAST({expression} AS TIME({a})) AS TIME({b})) AS p{a}_to_p{b}'
            for a in range(7) for b in range(7)) + suffix)
    sql_case('narrow_then_widen', 'SELECT ' + ', '.join(
        f'CAST(CAST(CAST({literal} AS TIME(6)) AS TIME({p})) AS TIME(6)) AS p6_to_p{p}_to_p6'
        for p in range(6)))
    sql_case('null_and_day_boundaries', "SELECT CAST(s AS TIME(3)) AS t3 FROM VALUES "
             "('00:00:00'), ('23:59:59.999999'), (CAST(NULL AS STRING)) AS data(s)")

    def field(name, typ, nullable=True):
        return {'name': name, 'type': typ, 'nullable': nullable, 'metadata': {}}
    def struct(*fields):
        return {'type': 'struct', 'fields': list(fields)}
    def merge_case(name, left, right):
        def run():
            left_j = spark._jsparkSession.parseDataType(json.dumps(left))
            right_j = spark._jsparkSession.parseDataType(json.dumps(right))
            result = left_j.merge(right_j, True)
            return {'schema': json.loads(result.json()), 'ddl': result.toDDL()}
        return case(name, run, operation='JVM StructType.merge(other, true)', left=left, right=right)
    for a, b in ((0, 0), (3, 3), (6, 6), (0, 3), (3, 6), (6, 3), (1, 2)):
        merge_case(f'merge_p{a}_p{b}', struct(field('t', f'time({a})', False)),
                   struct(field('t', f'time({b})', True)))
    merge_case('merge_distinct_field_names', struct(field('a', 'time(0)', False)),
               struct(field('b', 'time(6)', True)))
    merge_case('merge_time_and_null', struct(field('t', 'time(3)')),
               struct(field('t', 'void')))
    merge_case('merge_nested_array_mismatch', struct(field('a', {'type': 'array', 'elementType': 'time(0)', 'containsNull': False})),
               struct(field('a', {'type': 'array', 'elementType': 'time(6)', 'containsNull': True})))
    merge_case('merge_nested_struct_mismatch', struct(field('s', struct(field('t', 'time(3)')))),
               struct(field('s', struct(field('t', 'time(6)')))))
    merge_case('merge_nested_map_mismatch', struct(field('m', {'type': 'map', 'keyType': 'string', 'valueType': 'time(1)', 'valueContainsNull': False})),
               struct(field('m', {'type': 'map', 'keyType': 'string', 'valueType': 'time(2)', 'valueContainsNull': True})))
    report['completed'] = True
except Exception as error:
    report['fatal_error'] = exception(error, 'fatal.failure.txt')
    raise
finally:
    if spark is not None:
        spark.stop()
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
print(json.dumps({'completed': report.get('completed', False), 'cases': len(report['cases']),
                  'passed': sum(c['outcome'] == 'passed' for c in report['cases']),
                  'failed': sum(c['outcome'] == 'failed' for c in report['cases'])}))
