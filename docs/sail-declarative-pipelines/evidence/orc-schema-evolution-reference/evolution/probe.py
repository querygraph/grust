"""28 bounded Spark 4.2.1 ORC requested/inferred-schema observations."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback

import pyarrow as pa
import pyarrow.orc as orc
from pyspark import SparkContext
from pyspark.sql import SparkSession, types as T

ROOT = Path(__file__).resolve().parent
REFERENCE = Path('/tmp/sail-sdp-orc-bridge-reference')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(report):
    (ROOT / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


def values(array):
    if isinstance(array, pa.ChunkedArray):
        array = array.combine_chunks()
    dtype = array.type
    if pa.types.is_timestamp(dtype) or pa.types.is_time64(dtype) or pa.types.is_duration(dtype):
        return array.cast(pa.int64()).to_pylist()
    if pa.types.is_struct(dtype):
        columns = [values(array.field(i)) for i in range(dtype.num_fields)]
        valid = array.is_valid().to_pylist()
        return [dict(zip([f.name for f in dtype], [c[i] for c in columns])) if valid[i] else None
                for i in range(len(array))]
    if pa.types.is_list(dtype) or pa.types.is_large_list(dtype):
        child, offsets = values(array.values), array.offsets.to_pylist()
        return [child[offsets[i]:offsets[i + 1]] if array[i].is_valid else None
                for i in range(len(array))]
    if pa.types.is_map(dtype):
        keys, items, offsets = values(array.keys), values(array.items), array.offsets.to_pylist()
        return [list(zip(keys[offsets[i]:offsets[i + 1]], items[offsets[i]:offsets[i + 1]]))
                if array[i].is_valid else None for i in range(len(array))]
    return array.to_pylist()


def arrow_result(table):
    return {'schema': str(table.schema), 'num_rows': table.num_rows,
            'columns': [{'name': f.name, 'type': str(f.type), 'values': values(table.column(i))}
                        for i, f in enumerate(table.schema)]}


def error_record(error):
    try:
        condition = error.getCondition()
    except (AttributeError, TypeError):
        condition = None
    return {'python_type': type(error).__name__, 'condition': condition,
            'message': str(error), 'traceback': traceback.format_exc()}


def replace(schema, name, dtype):
    return T.StructType([T.StructField(f.name, dtype if f.name == name else f.dataType,
                                      f.nullable, f.metadata) for f in schema])


def main():
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Bounded Spark reference only; no Sail runtime qualification or production policy selection',
              'spark_source_pin': PIN, 'sail_source_pin': '27ab945aaa3046d05a1f4aeb1e651fddf11db927',
              'grust_baseline': '861e5214', 'script_sha256': sha(Path(__file__)),
              'python_pid': os.getpid(), 'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
              'status': 'starting', 'fixtures': {}, 'cases': []}
    save(report)
    for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
                'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
        os.environ.pop(key, None)
    os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
    os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
    session = gateway = process = None
    try:
        session = (SparkSession.builder.remote('local[1]')
                   .config('spark.ui.enabled', 'false')
                   .config('spark.driver.memory', '512m')
                   .config('spark.sql.shuffle.partitions', '1')
                   .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri())
                   .config('spark.sql.session.timeZone', 'UTC')
                   .config('spark.sql.orc.impl', 'native')
                   .config('spark.sql.caseSensitive', 'true')
                   .config('spark.sql.orc.enableNestedColumnVectorizedReader', 'true')
                   .getOrCreate())
        gateway = SparkContext._gateway
        process = gateway.proc
        assert process is not None, 'probe must own its gateway JVM'
        java = SparkContext._jvm.java
        runtime = java.lang.management.ManagementFactory.getRuntimeMXBean()
        report['java'] = {
            'gateway_pid': process.pid, 'actual_pid': int(runtime.getPid()),
            'default_timezone_id': java.util.TimeZone.getDefault().getID(),
            'user_timezone_property': java.lang.System.getProperty('user.timezone'),
            'format_locale': java.util.Locale.getDefault(java.util.Locale.Category.FORMAT).toLanguageTag(),
            'runtime_version': java.lang.System.getProperty('java.runtime.version'),
            'vendor': java.lang.System.getProperty('java.vendor'),
            'oldmapping_property': java.lang.System.getProperty('sun.timezone.ids.oldmapping'),
            'tzdb_versions': list(java.time.zone.ZoneRulesProvider.getVersions('UTC').keySet())}
        report['spark_version'] = session.version
        assert session.version == '4.2.1'
        assert report['java']['default_timezone_id'] == report['java']['user_timezone_property'] == 'UTC'
        assert report['java']['format_locale'] == 'en-US'
        assert report['java']['runtime_version'] == '20.0.2+9-78'
        assert report['java']['tzdb_versions'] == ['2023c']
        assert report['java']['oldmapping_property'] == 'false'
        report['time_enabled_before_override'] = session.conf.get('spark.sql.timeType.enabled')
        session.conf.set('spark.sql.timeType.enabled', 'true')
        settings = ['spark.sql.session.timeZone', 'spark.sql.orc.impl', 'spark.sql.caseSensitive',
                    'spark.sql.orc.enableVectorizedReader', 'spark.sql.orc.enableNestedColumnVectorizedReader',
                    'spark.sql.orc.mergeSchema', 'spark.sql.orc.filterPushdown', 'spark.sql.ansi.enabled',
                    'spark.sql.timestampType', 'spark.sql.timeType.enabled', 'spark.sql.shuffle.partitions',
                    'spark.sql.files.ignoreCorruptFiles']
        report['config'] = {name: session.conf.get(name) for name in settings}
        report['status'] = 'fixtures'
        save(report)
        print(json.dumps({'phase': 'started', 'java': report['java']}), flush=True)
        original = json.loads((REFERENCE / 'expected.json').read_text())
        report['original_expected_sha256'] = sha(REFERENCE / 'expected.json')
        old = {c['name']: c for c in original['cases']}
        paths, schemas = {}, {}

        def record_fixture(name, path, source=None):
            paths[name] = path
            report['fixtures'][name] = {'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size,
                                         'physical_arrow': arrow_result(orc.ORCFile(path).read())}
            if source is not None:
                report['fixtures'][name]['source'] = source
            save(report)

        for name in ['time_precisions', 'intervals']:
            original_path = next((REFERENCE / 'data' / name).glob('*.orc'))
            target = ROOT / 'inputs' / f'{name}.orc'
            target.parent.mkdir(exist_ok=True)
            assert not target.exists(), target
            shutil.copyfile(original_path, target)
            record_fixture(name, target, {'original_path': str(original_path), 'original_sha256': sha(original_path),
                                         'original_sql': old[name]['sql'], 'original_schema': old[name]['source_schema']})
            schemas[name] = T.StructType.fromJson(old[name]['read_schema'])

        def fixture(name, sql):
            frame = session.sql(sql)
            source = {'sql': sql, 'schema': frame.schema.jsonValue()}
            directory = ROOT / 'data' / name
            frame.coalesce(1).write.mode('error').orc(str(directory))
            files = list(directory.glob('*.orc'))
            assert len(files) == 1, files
            record_fixture(name, files[0], source)
            schemas[name] = frame.schema

        fixture('integers', '''SELECT * FROM VALUES
            (0, -129, -2147483649L), (1, -128, -2147483648L),
            (2, 127, 2147483647L), (3, 128, 2147483648L), (4, 32768, 128L),
            (5, CAST(NULL AS INT), CAST(NULL AS BIGINT)) AS v(id, i, b)''')
        fixture('mixed_case', "SELECT IF(id = 0, 11, NULL) AS Foo, IF(id = 0, named_struct('Bar', 22), NULL) AS st FROM range(2)")
        fixture('ambiguous_top', 'SELECT 11 AS Foo, 22 AS foo')
        fixture('ambiguous_nested', "SELECT named_struct('Bar', 11, 'bar', 22) AS st")
        fixture('hive_names', "SELECT 11 AS _col0, 'eleven' AS _col1 UNION ALL SELECT NULL, NULL")
        fixture('merge_time0', "SELECT CAST('12:34:56.123456' AS TIME(0)) AS t")
        fixture('merge_time0_extra', "SELECT CAST('12:34:56.123456' AS TIME(0)) AS t, 11 AS eleventh")
        fixture('merge_time3', "SELECT CAST('12:34:56.123456' AS TIME(3)) AS t")
        fixture('merge_interval_year', "SELECT INTERVAL '2' YEAR AS x, INTERVAL '3' DAY AS y")
        fixture('merge_interval_month', "SELECT INTERVAL '14' MONTH AS x, INTERVAL '1.000001' SECOND AS y")
        fixture('merge_interval_cross_family', "SELECT INTERVAL '3' DAY AS x, INTERVAL '1.000001' SECOND AS y")
        for label, first, last in [
            ('eleventh_field', 'merge_time0', 'merge_time0_extra'),
            ('time_conflict', 'merge_time0', 'merge_time3'),
            ('interval_union', 'merge_interval_year', 'merge_interval_month'),
            ('interval_family_conflict', 'merge_interval_year', 'merge_interval_cross_family')]:
            directory = ROOT / 'multi' / label
            directory.mkdir(parents=True)
            members = []
            for index in range(11):
                source_name = last if index == 10 else first
                target = directory / f'part-{index:05d}.orc'
                shutil.copyfile(paths[source_name], target)
                members.append({'file': str(target), 'source_fixture': source_name, 'sha256': sha(target)})
            paths[label] = directory
            report.setdefault('multi_file_inputs', {})[label] = members
        save(report)
        cases = []

        def case(name, fixture_name=None, schema=None, *, vectorized=True, case_sensitive=True,
                 projection=None, merge=None, sql=None):
            cases.append({'name': name, 'fixture': fixture_name, 'schema': schema, 'vectorized': vectorized,
                          'case_sensitive': case_sensitive, 'projection': projection, 'merge': merge, 'sql': sql})

        time_schema = schemas['time_precisions']
        case('time0_fractional_baseline', 'time_precisions', time_schema)
        for p in [3, 6]:
            for vector in [True, False]:
                case(f'time0_requested_p{p}_vector_{vector}', 'time_precisions', replace(time_schema, 't0', T.TimeType(p)), vectorized=vector)
        time_path = paths['time_precisions'].as_uri()
        case('time0_sql_cast_controls', sql=f"SELECT id, CAST(t0 AS TIME(3)) AS p3, CAST(t0 AS TIME(6)) AS p6 FROM orc.`{time_path}`")
        interval_schema = schemas['intervals']
        numeric = old['intervals']['numeric_projection_sql']
        for name, dtype in [('ym', T.YearMonthIntervalType(0, 0)), ('dt', T.DayTimeIntervalType(0, 0))]:
            for vector in [True, False]:
                case(f'interval_narrow_{name}_vector_{vector}', 'intervals', replace(interval_schema, name, dtype), vectorized=vector, projection=numeric)
        widened = replace(replace(interval_schema, 'y', T.YearMonthIntervalType()), 'd', T.DayTimeIntervalType())
        case('interval_widen_qualifiers', 'intervals', widened, projection=numeric)
        int_schema = schemas['integers']
        for name, dtype in [('i', T.LongType()), ('b', T.IntegerType())]:
            for vector in [True, False]:
                case(f'integer_requested_{name}_{dtype.simpleString()}_vector_{vector}', 'integers', replace(int_schema, name, dtype), vectorized=vector)
        case('integer_int_to_byte_boundaries', 'integers', replace(int_schema, 'i', T.ByteType()))
        mixed_requested = T.StructType([T.StructField('foo', T.IntegerType()), T.StructField('ST', T.StructType([T.StructField('bar', T.IntegerType())]))])
        for sensitivity in [True, False]:
            case(f'mixed_nested_case_sensitive_{sensitivity}', 'mixed_case', mixed_requested, case_sensitive=sensitivity)
        missing = T.StructType([T.StructField('Foo', T.IntegerType()), T.StructField('st', T.StructType([
            T.StructField('Bar', T.IntegerType()), T.StructField('absent', T.IntegerType())])), T.StructField('absent', T.IntegerType())])
        case('top_and_nested_missing_fields', 'mixed_case', missing)
        case('ambiguous_top_case_insensitive', 'ambiguous_top', T.StructType([T.StructField('foo', T.IntegerType())]), case_sensitive=False)
        case('ambiguous_nested_case_insensitive', 'ambiguous_nested', T.StructType([T.StructField('st', T.StructType([T.StructField('bar', T.IntegerType())]))]), case_sensitive=False)
        case('eleventh_field_merge_false', 'eleventh_field', merge=False)
        case('eleventh_field_merge_true', 'eleventh_field', merge=True)
        case('eleventh_time_precision_conflict', 'time_conflict', merge=True)
        interval_merge_projection = ['CAST(CAST(x AS INTERVAL YEAR TO MONTH) AS INT) AS x_months',
            'CAST(CAST(CAST(y AS INTERVAL DAY TO SECOND) AS DECIMAL(30,6)) * 1000000 AS BIGINT) AS y_micros']
        case('eleventh_interval_qualifier_union', 'interval_union', merge=True, projection=interval_merge_projection)
        case('eleventh_interval_family_conflict', 'interval_family_conflict', merge=True)
        renamed = T.StructType([T.StructField('first', T.IntegerType()), T.StructField('second', T.StringType())])
        case('hive_fallback_renamed_fields', 'hive_names', renamed)
        case('hive_fallback_project_second', 'hive_names', renamed, projection=['second'])
        assert len(cases) == 28, len(cases)
        report['case_plan'] = [{**c, 'schema': c['schema'].jsonValue() if c['schema'] is not None else None} for c in cases]
        report['status'] = 'probing'
        save(report)
        for item in cases:
            session.conf.set('spark.sql.orc.enableVectorizedReader', str(item['vectorized']).lower())
            session.conf.set('spark.sql.caseSensitive', str(item['case_sensitive']).lower())
            result = {'name': item['name'], 'config': {name: session.conf.get(name) for name in settings},
                      'fixture': item['fixture'], 'requested_schema': item['schema'].jsonValue() if item['schema'] is not None else None,
                      'projection': item['projection'], 'merge_option': item['merge'], 'sql': item['sql'],
                      'stage': 'construct', 'status': 'running'}
            report['cases'].append(result)
            try:
                if item['sql'] is not None:
                    frame = session.sql(item['sql'])
                else:
                    reader = session.read
                    if item['schema'] is not None:
                        reader = reader.schema(item['schema'])
                    if item['merge'] is not None:
                        reader = reader.option('mergeSchema', str(item['merge']).lower())
                    frame = reader.orc(str(paths[item['fixture']]))
                result['stage'] = 'schema'
                result['read_schema'] = frame.schema.jsonValue()
                if item['projection']:
                    frame = frame.selectExpr(*item['projection'])
                if 'id' in frame.columns:
                    frame = frame.orderBy('id')
                result['output_schema'] = frame.schema.jsonValue()
                result['stage'] = 'explain'
                plan = io.StringIO()
                with redirect_stdout(plan):
                    frame.explain(mode='formatted')
                result['physical_plan'] = plan.getvalue()
                result['stage'] = 'materialize_to_arrow'
                result['arrow'] = arrow_result(frame.toArrow())
                result['status'] = 'success'
            except Exception as error:
                result['status'] = 'error'
                result['error'] = error_record(error)
            save(report)
            print(json.dumps({'phase': 'case', 'name': result['name'], 'status': result['status'],
                              'stage': result['stage'], 'condition': result.get('error', {}).get('condition')}), flush=True)
        for receipt in report['fixtures'].values():
            assert sha(Path(receipt['path'])) == receipt['sha256']
            if receipt.get('source', {}).get('original_path'):
                assert sha(Path(receipt['source']['original_path'])) == receipt['source']['original_sha256']
        assert sha(REFERENCE / 'expected.json') == report['original_expected_sha256']
        assert len(report['cases']) == 28
        report['status'] = 'completed'
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        if session is not None:
            session.stop()
        if gateway is not None:
            gateway.shutdown()
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            report['owned_gateway_exit_code'] = process.returncode
        save(report)
        print(json.dumps({'phase': 'finished', 'status': report['status'], 'path': str(ROOT / 'results.json')}), flush=True)


if __name__ == '__main__':
    main()
