"""Bounded Spark 4.2.1 ORC requested-schema timestamp compatibility probe."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback

import pyarrow as pa
from pyspark import SparkContext
from pyspark.sql import SparkSession, types as T

ROOT = Path(__file__).resolve().parent
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(value):
    (ROOT / 'results.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def values(array):
    if isinstance(array, pa.ChunkedArray):
        array = array.combine_chunks()
    dtype = array.type
    if pa.types.is_timestamp(dtype):
        return array.cast(pa.int64()).to_pylist()
    if pa.types.is_struct(dtype):
        columns = [values(array.field(i)) for i in range(dtype.num_fields)]
        valid = array.is_valid().to_pylist()
        return [dict(zip([f.name for f in dtype], [c[i] for c in columns])) if valid[i] else None
                for i in range(len(array))]
    if pa.types.is_list(dtype) or pa.types.is_large_list(dtype):
        child = values(array.values)
        offsets = array.offsets.to_pylist()
        return [child[offsets[i]:offsets[i + 1]] if array[i].is_valid else None
                for i in range(len(array))]
    if pa.types.is_map(dtype):
        keys, items = values(array.keys), values(array.items)
        offsets = array.offsets.to_pylist()
        return [list(zip(keys[offsets[i]:offsets[i + 1]], items[offsets[i]:offsets[i + 1]]))
                if array[i].is_valid else None for i in range(len(array))]
    return array.to_pylist()


def arrow_result(table):
    return {'schema': str(table.schema), 'num_rows': table.num_rows,
            'columns': [{'name': f.name, 'type': str(f.type), 'values': values(table.column(i))}
                        for i, f in enumerate(table.schema)]}


def error_record(error):
    condition = None
    try:
        condition = error.getCondition()
    except (AttributeError, TypeError):
        pass
    return {'python_type': type(error).__name__, 'condition': condition,
            'message': str(error), 'traceback': traceback.format_exc()}


def replace(schema, name, dtype):
    return T.StructType([T.StructField(f.name, dtype if f.name == name else f.dataType,
                                      f.nullable, f.metadata) for f in schema])


def main():
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Fresh native ORC reads with supplied schemas; no Sail runtime qualification or production policy selection',
              'spark_source_pin': PIN, 'script_sha256': sha(Path(__file__)),
              'python_pid': os.getpid(), 'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
              'status': 'starting', 'cases': []}
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
        assert report['java']['default_timezone_id'] == 'UTC'
        assert report['java']['user_timezone_property'] == 'UTC'
        assert report['java']['format_locale'] == 'en-US'
        assert report['java']['runtime_version'] == '20.0.2+9-78'
        assert report['java']['tzdb_versions'] == ['2023c']
        assert report['java']['oldmapping_property'] == 'false'
        report['config'] = {name: session.conf.get(name) for name in [
            'spark.sql.session.timeZone', 'spark.sql.orc.impl', 'spark.sql.caseSensitive',
            'spark.sql.orc.enableNestedColumnVectorizedReader', 'spark.sql.orc.mergeSchema',
            'spark.sql.orc.filterPushdown', 'spark.sql.ansi.enabled', 'spark.sql.timestampType',
            'spark.sql.shuffle.partitions', 'spark.sql.files.ignoreCorruptFiles']}
        save(report)
        print(json.dumps({'phase': 'started', 'java': report['java']}), flush=True)
        ltz = "CAST('2020-01-02 03:04:05.123456' AS TIMESTAMP_LTZ)"
        ntz = "CAST('2021-06-07 08:09:10.654321' AS TIMESTAMP_NTZ)"
        fields = [('ltz', ltz), ('ntz', ntz),
                  ('st', f"named_struct('ltz', {ltz}, 'ntz', {ntz})"),
                  ('la', f'array({ltz}, CAST(NULL AS TIMESTAMP_LTZ))'),
                  ('na', f'array({ntz}, CAST(NULL AS TIMESTAMP_NTZ))'),
                  ('lm', f"map('value', {ltz}, 'null', CAST(NULL AS TIMESTAMP_LTZ))"),
                  ('nm', f"map('value', {ntz}, 'null', CAST(NULL AS TIMESTAMP_NTZ))")]
        sql = 'SELECT ' + ', '.join(f'IF(id = 0, {expr}, NULL) AS {name}' for name, expr in fields) + ' FROM range(2)'
        (ROOT / 'fixture.sql').write_text(sql + '\n')
        source = session.sql(sql)
        schema = source.schema
        report['source'] = {'sql': sql, 'schema': schema.jsonValue(),
                            'arrow': arrow_result(source.toArrow())}
        directory = ROOT / 'data' / 'mixed_timestamps'
        source.coalesce(1).write.mode('error').orc(str(directory))
        fixtures = list(directory.glob('*.orc'))
        assert len(fixtures) == 1, fixtures
        fixture = fixtures[0]
        report['fixture'] = {'path': str(fixture), 'sha256': sha(fixture), 'size': fixture.stat().st_size}
        report['inferred_schema'] = session.read.orc(str(fixture)).schema.jsonValue()
        report['status'] = 'probing'
        save(report)
        reorder = lambda s: T.StructType([s['ntz'], s['ltz']] + [f for f in s if f.name not in ['ltz', 'ntz']])
        nested = schema['st'].dataType
        cases = [
            ('exact_schema', schema, None),
            ('scalar_ltz_to_ntz', replace(schema, 'ltz', T.TimestampNTZType()), None),
            ('scalar_ntz_to_ltz', replace(schema, 'ntz', T.TimestampType()), None),
            ('requested_only_second_ntz', T.StructType([schema['ntz']]), None),
            ('exact_schema_project_only_second_ntz', schema, ['ntz']),
            ('reordered_matching_names', reorder(schema), None),
            ('missing_ltz_appended', T.StructType(list(schema) + [T.StructField('absent_ltz', T.TimestampType())]), None),
            ('missing_ntz_appended', T.StructType(list(schema) + [T.StructField('absent_ntz', T.TimestampNTZType())]), None),
            ('nested_struct_swaps', replace(schema, 'st', T.StructType([
                T.StructField('ltz', T.TimestampNTZType()), T.StructField('ntz', T.TimestampType())])), None),
            ('nested_struct_reordered_matching_names', replace(schema, 'st', T.StructType([nested['ntz'], nested['ltz']])), None),
            ('array_swaps', replace(replace(schema, 'la', T.ArrayType(T.TimestampNTZType())),
                                    'na', T.ArrayType(T.TimestampType())), None),
            ('map_swaps', replace(replace(schema, 'lm', T.MapType(T.StringType(), T.TimestampNTZType())),
                                  'nm', T.MapType(T.StringType(), T.TimestampType())), None)]
        assert len(cases) * 2 == 24
        for vectorized in [True, False]:
            session.conf.set('spark.sql.orc.enableVectorizedReader', str(vectorized).lower())
            for name, requested, projection in cases:
                result = {'name': name, 'vectorized': vectorized,
                          'actual_vectorized_config': session.conf.get('spark.sql.orc.enableVectorizedReader'),
                          'nested_vectorized_config': session.conf.get('spark.sql.orc.enableNestedColumnVectorizedReader'),
                          'requested_schema': requested.jsonValue(), 'projection': projection,
                          'stage': 'construct', 'status': 'running'}
                report['cases'].append(result)
                try:
                    frame = session.read.schema(requested).orc(str(fixture))
                    if projection is not None:
                        frame = frame.select(*projection)
                    result['stage'] = 'schema'
                    result['analyzed_schema'] = frame.schema.jsonValue()
                    result['stage'] = 'materialize_to_arrow'
                    result['arrow'] = arrow_result(frame.toArrow())
                    result['status'] = 'success'
                except Exception as error:
                    result['status'] = 'error'
                    result['error'] = error_record(error)
                save(report)
                print(json.dumps({'phase': 'case', 'name': name, 'vectorized': vectorized,
                                  'status': result['status'], 'stage': result['stage'],
                                  'condition': result.get('error', {}).get('condition')}), flush=True)
        assert sha(fixture) == report['fixture']['sha256']
        assert len(report['cases']) == 24
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
