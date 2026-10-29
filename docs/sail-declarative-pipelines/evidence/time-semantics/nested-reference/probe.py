"""Spark 4.2.1 nested TIME CAST oracle. One local[1] process; no Sail execution."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import traceback

ROOT = Path(__file__).resolve().parent
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
SAIL = Path('/Users/alexy/src/sail-pipelines-proposal')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
import pyarrow as pa
import pyspark
from pyspark.sql import SparkSession

report = {'created_at': datetime.now(timezone.utc).isoformat(), 'spark_source_pin': PIN,
          'pyspark_version': pyspark.__version__, 'pyspark_path': pyspark.__file__,
          'pyarrow_version': pa.__version__, 'sources': [], 'cases': [],
          'qualification': 'Installed Spark runtime only. No Sail execution. Installed jar version/hash does not attest source-pin build provenance.'}

def save():
    (ROOT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})

cast_path = 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala'
for name, path, first, last in (
    ('spark-recursive-cast', cast_path, 1225, 1286),
    ('spark-time-cast', cast_path, 828, 837),
    ('spark-codegen-identity', cast_path, 1348, 1358),
    ('spark-recursive-codegen', cast_path, 2284, 2392),
    ('spark-time-codegen', cast_path, 1497, 1529),
    ('spark-time-type', 'sql/api/src/main/scala/org/apache/spark/sql/types/TimeType.scala', 23, 59),
    ('spark-time-config', 'sql/catalyst/src/main/scala/org/apache/spark/sql/internal/SQLConf.scala', 7435, 7442),
):
    data = git(SPARK, 'show', f'{PIN}:{path}')
    excerpt = b''.join(data.splitlines(keepends=True)[first - 1:last])
    filename = name + '.txt'
    (ROOT / filename).write_bytes(excerpt)
    report['sources'].append({'repository': str(SPARK), 'commit': PIN, 'path': path,
        'first_line': first, 'last_line': last, 'file': filename,
        'git_blob': git(SPARK, 'rev-parse', f'{PIN}:{path}').decode().strip(),
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'excerpt_sha256': hashlib.sha256(excerpt).hexdigest()})
for name, path in (
    ('sail-expression-cast-working', 'crates/sail-plan/src/resolver/expression/cast.rs'),
    ('sail-type-resolver-working', 'crates/sail-plan/src/resolver/data_type.rs'),
    ('sail-recursive-array-cast-working', 'crates/sail-common-datafusion/src/array/record_batch.rs'),
):
    data = (SAIL / path).read_bytes()
    filename = name + '.rs'
    (ROOT / filename).write_bytes(data)
    report['sources'].append({'repository': str(SAIL), 'head_at_capture': git(SAIL, 'rev-parse', 'HEAD').decode().strip(),
        'kind': 'working-file snapshot, may include uncommitted work', 'path': path, 'file': filename,
        'sha256': hashlib.sha256(data).hexdigest()})
jar_dir = Path(pyspark.__file__).parent / 'jars'
report['runtime_jars'] = [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                         for pattern in ('spark-sql-api_*.jar', 'spark-catalyst_*.jar', 'spark-sql_*.jar')
                         for p in sorted(jar_dir.glob(pattern))]

# Serialize physical integer TIME values at every nesting depth; never use datetime.time.
def integer_value(array, index):
    if not array[index].is_valid:
        return None
    typ = array.type
    if pa.types.is_time64(typ) or pa.types.is_time32(typ):
        return array.slice(index, 1).cast(pa.int64()).to_pylist()[0]
    if pa.types.is_list(typ) or pa.types.is_large_list(typ):
        start, end = array.offsets[index].as_py(), array.offsets[index + 1].as_py()
        return [integer_value(array.values, i) for i in range(start, end)]
    if pa.types.is_struct(typ):
        return {f.name: integer_value(array.field(i), index) for i, f in enumerate(typ)}
    if pa.types.is_map(typ):
        start, end = array.offsets[index].as_py(), array.offsets[index + 1].as_py()
        return [[integer_value(array.keys, i), integer_value(array.items, i)] for i in range(start, end)]
    return array[index].as_py()

s = None
try:
    s = (SparkSession.builder.master('local[1]').appName('sail-nested-time-semantic-reference')
         .config('spark.ui.enabled', 'false').config('spark.driver.memory', '512m')
         .config('spark.executor.memory', '512m').config('spark.default.parallelism', '1')
         .config('spark.sql.shuffle.partitions', '1').config('spark.sql.session.timeZone', 'UTC')
         .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri()).getOrCreate())
    s.sparkContext.setLogLevel('ERROR')
    report['spark_version'] = s.version
    report['master'] = s.sparkContext.master
    report['initial_time_enabled'] = s.conf.get('spark.sql.timeType.enabled')
    s.conf.set('spark.sql.timeType.enabled', 'true')
    report['config'] = {k:s.conf.get(k) for k in ('spark.sql.timeType.enabled', 'spark.sql.ansi.enabled', 'spark.sql.codegen.wholeStage', 'spark.sql.session.timeZone', 'spark.sql.shuffle.partitions')}
    assert s.version == '4.2.1'
    t0 = 'CAST(s AS TIME(0))'
    n0 = 'CAST(NULL AS TIME(0))'
    pair = f"named_struct('changed', {t0}, 'kept', {t0})"
    cases = [
        ('array_change', f'CAST(array({t0}, {n0}) AS ARRAY<TIME(3)>)', [45296123000000, None]),
        ('array_identity', f'CAST(array({t0}, {n0}) AS ARRAY<TIME(0)>)', [45296123456000, None]),
        ('struct_mixed', f'CAST({pair} AS STRUCT<changed:TIME(3), kept:TIME(0)>)', {'changed':45296123000000, 'kept':45296123456000}),
        ('struct_identity', f'CAST({pair} AS STRUCT<changed:TIME(0), kept:TIME(0)>)', {'changed':45296123456000, 'kept':45296123456000}),
        ('map_value_change', f"CAST(map('clock', {t0}, 'missing', {n0}) AS MAP<STRING,TIME(3)>)", [['clock',45296123000000],['missing',None]]),
        ('map_value_identity', f"CAST(map('clock', {t0}, 'missing', {n0}) AS MAP<STRING,TIME(0)>)", [['clock',45296123456000],['missing',None]]),
        ('map_key_change', f"CAST(map({t0}, 'value') AS MAP<TIME(3),STRING>)", [[45296123000000,'value']]),
        ('map_key_identity_value_change', f'CAST(map({t0}, {t0}) AS MAP<TIME(0),TIME(3)>)', [[45296123456000,45296123000000]]),
        ('array_struct_mixed', f'CAST(array({pair}, CAST(NULL AS STRUCT<changed:TIME(0), kept:TIME(0)>)) AS ARRAY<STRUCT<changed:TIME(3), kept:TIME(0)>>)', [{'changed':45296123000000,'kept':45296123456000},None]),
        ('struct_positional_rename', f'CAST({pair} AS STRUCT<renamed:TIME(3), unchanged:TIME(0)>)', {'renamed':45296123000000,'unchanged':45296123456000}),
    ]
    for name, expression, expected in cases:
        query = "WITH source AS (SELECT concat('12:34:56.', cast(id AS STRING)) AS s FROM range(123456, 123457)) SELECT " + expression + ' AS value FROM source'
        case = {'name':name, 'sql':query, 'expected_integer_value':expected}
        report['cases'].append(case)
        try:
            frame = s.sql(query)
            case['schema'] = json.loads(frame._jdf.schema().json())
            case['schema_ddl'] = frame._jdf.schema().toDDL()
            save()
            table = frame.toArrow()
            case['arrow_schema'] = str(table.schema)
            case['integer_values'] = [integer_value(table.column(0).combine_chunks(), i) for i in range(table.num_rows)]
            case['optimized_plan'] = frame._jdf.queryExecution().optimizedPlan().toString()
            case['outcome'] = 'passed'
            case['expectation_passed'] = case['integer_values'] == [expected]
        except Exception as error:
            case['outcome'] = 'failed'
            case['exception'] = {'python_type':type(error).__name__, 'message':str(error)}
            filename = name + '.failure.txt'
            (ROOT / filename).write_text(traceback.format_exc())
            case['exception']['traceback'] = filename
        finally:
            save()
    report['completed'] = True
except Exception as error:
    report['fatal_exception'] = str(error)
    (ROOT / 'fatal.failure.txt').write_text(traceback.format_exc())
    raise
finally:
    if s is not None:
        s.stop()
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
print(json.dumps({'completed':report.get('completed',False),'cases':len(report['cases']),
                  'expectations_passed':sum(c.get('expectation_passed',False) for c in report['cases'])}))
