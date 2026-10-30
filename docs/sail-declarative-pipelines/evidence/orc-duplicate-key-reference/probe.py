"""Four bounded Spark 4.2.1 ORC duplicate-name/map-key observations."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import traceback

import pyarrow as pa
import pyarrow.orc as orc
from pyspark import SparkContext
from pyspark.sql import SparkSession, types as T

ROOT = Path(__file__).resolve().parent
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(report):
    (ROOT / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


def arrow_result(table):
    # Keep duplicate physical field names by ordinal instead of dict conversion.
    return {'schema': str(table.schema), 'num_rows': table.num_rows,
            'columns': [{'ordinal': i, 'name': field.name, 'type': str(field.type),
                         'nullable': field.nullable, 'values': table.column(i).to_pylist()}
                        for i, field in enumerate(table.schema)]}


def error_record(error):
    try:
        condition = error.getCondition()
    except (AttributeError, TypeError):
        condition = None
    return {'python_type': type(error).__name__, 'condition': condition,
            'message': str(error), 'traceback': traceback.format_exc()}


def main():
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Bounded Spark reference only; no Sail runtime or general map-key conversion guarantee',
              'spark_source_pin': PIN, 'script_sha256': sha(Path(__file__)),
              'python_pid': os.getpid(), 'pyarrow_version': pa.__version__,
              'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
              'status': 'starting', 'fixtures': {}, 'cases': []}
    save(report)
    for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
                'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
        os.environ.pop(key, None)
    os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
    os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
    session = gateway = process = None
    try:
        inputs = ROOT / 'inputs'
        inputs.mkdir()
        duplicate = pa.Table.from_arrays(
            [pa.array([11], type=pa.int32()), pa.array([22], type=pa.int32())],
            names=['dup', 'dup'])
        map_table = pa.Table.from_arrays(
            [pa.array([[(1, 'one'), (2147483648, 'overflow')]],
                      type=pa.map_(pa.int64(), pa.string()))], names=['m'])
        paths = {}
        for name, table in [('duplicate_exact_top', duplicate), ('map_long_keys', map_table)]:
            fixture = {'generator': 'pyarrow.orc.write_table', 'input_arrow': arrow_result(table),
                       'stage': 'write', 'status': 'running'}
            report['fixtures'][name] = fixture
            path = inputs / f'{name}.orc'
            try:
                assert not path.exists()
                orc.write_table(table, path)
                fixture.update({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size,
                                'stage': 'physical_read'})
                physical = orc.ORCFile(path)
                fixture['physical_schema'] = str(physical.schema)
                fixture['physical_arrow'] = arrow_result(physical.read())
                fixture['status'] = 'success'
                paths[name] = path
            except Exception as error:
                fixture['status'] = 'error'
                fixture['error'] = error_record(error)
                if path.exists():
                    fixture.update({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
            save(report)
            print(json.dumps({'phase': 'fixture', 'name': name, 'status': fixture['status']}), flush=True)

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
        gateway, java = SparkContext._gateway, SparkContext._jvm.java
        process = gateway.proc
        assert process is not None, 'probe must own its gateway JVM'
        runtime = java.lang.management.ManagementFactory.getRuntimeMXBean()
        report['java'] = {'gateway_pid': process.pid, 'actual_pid': int(runtime.getPid()),
                          'default_timezone_id': java.util.TimeZone.getDefault().getID(),
                          'user_timezone_property': java.lang.System.getProperty('user.timezone'),
                          'format_locale': java.util.Locale.getDefault(java.util.Locale.Category.FORMAT).toLanguageTag(),
                          'runtime_version': java.lang.System.getProperty('java.runtime.version'),
                          'vendor': java.lang.System.getProperty('java.vendor'),
                          'oldmapping_property': java.lang.System.getProperty('sun.timezone.ids.oldmapping'),
                          'tzdb_versions': list(java.time.zone.ZoneRulesProvider.getVersions('UTC').keySet())}
        report['spark_version'] = session.version
        assert session.version == '4.2.1'
        assert report['java']['gateway_pid'] == report['java']['actual_pid']
        assert report['java']['default_timezone_id'] == report['java']['user_timezone_property'] == 'UTC'
        assert report['java']['format_locale'] == 'en-US'
        assert report['java']['runtime_version'] == '20.0.2+9-78'
        assert report['java']['tzdb_versions'] == ['2023c']
        assert report['java']['oldmapping_property'] == 'false'
        settings = ['spark.sql.session.timeZone', 'spark.sql.orc.impl', 'spark.sql.caseSensitive',
                    'spark.sql.orc.enableVectorizedReader', 'spark.sql.orc.enableNestedColumnVectorizedReader',
                    'spark.sql.orc.mergeSchema', 'spark.sql.orc.filterPushdown', 'spark.sql.ansi.enabled',
                    'spark.sql.timestampType', 'spark.sql.timeType.enabled', 'spark.sql.shuffle.partitions',
                    'spark.sql.files.ignoreCorruptFiles', 'spark.sql.mapKeyDedupPolicy']
        report['config'] = {name: session.conf.get(name) for name in settings}
        java_conf = SparkContext._jvm.org.apache.spark.SparkEnv.get().conf()
        report['spark_context'] = {'master': java_conf.get('spark.master'),
                                   'driver_memory': java_conf.get('spark.driver.memory')}
        assert report['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
        print(json.dumps({'phase': 'started', 'java': report['java']}), flush=True)
        duplicate_schema = T.StructType([T.StructField('dup', T.IntegerType())])
        map_schema = T.StructType([T.StructField('m', T.MapType(T.IntegerType(), T.StringType()))])
        plans = [
            ('duplicate_sensitive_true', 'duplicate_exact_top', duplicate_schema, True, True, None),
            ('duplicate_sensitive_false', 'duplicate_exact_top', duplicate_schema, False, True, None),
            ('map_key_narrow_vector_true', 'map_long_keys', map_schema, True, True, 'explode(m) AS (key, value)'),
            ('map_key_narrow_vector_false', 'map_long_keys', map_schema, True, False, 'explode(m) AS (key, value)'),
        ]
        report['status'] = 'probing'
        save(report)
        for name, fixture, schema, sensitivity, vectorized, projection in plans:
            session.conf.set('spark.sql.caseSensitive', str(sensitivity).lower())
            session.conf.set('spark.sql.orc.enableVectorizedReader', str(vectorized).lower())
            result = {'name': name, 'fixture': fixture, 'requested_schema': schema.jsonValue(),
                      'projection': projection, 'config': {key: session.conf.get(key) for key in settings},
                      'stage': 'construct', 'status': 'running'}
            report['cases'].append(result)
            if fixture not in paths:
                result.update({'status': 'fixture_unavailable', 'stage': 'fixture_generation',
                               'reason': 'No successful physical fixture; this is not a Spark observation'})
            else:
                try:
                    frame = session.read.schema(schema).orc(str(paths[fixture]))
                    result['stage'] = 'read_schema'
                    result['read_schema'] = frame.schema.jsonValue()
                    result['stage'] = 'projection'
                    output = frame.selectExpr(projection) if projection else frame
                    result['output_schema'] = output.schema.jsonValue()
                    result['stage'] = 'explain'
                    plan = io.StringIO()
                    with redirect_stdout(plan):
                        output.explain(mode='formatted')
                    result['physical_plan'] = plan.getvalue()
                    result['stage'] = 'materialize_to_arrow'
                    result['arrow'] = arrow_result(output.toArrow())
                    result['status'] = 'success'
                except Exception as error:
                    result['status'] = 'error'
                    result['error'] = error_record(error)
            save(report)
            print(json.dumps({'phase': 'case', 'name': name, 'status': result['status'],
                              'stage': result['stage']}), flush=True)
        for name, path in paths.items():
            assert sha(path) == report['fixtures'][name]['sha256']
        report['status'] = 'completed'
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        for name, action in [('session_stop', lambda: session.stop() if session is not None else None),
                             ('gateway_shutdown', lambda: gateway.shutdown() if gateway is not None else None)]:
            try:
                action()
            except Exception:
                report.setdefault('cleanup_errors', {})[name] = traceback.format_exc()
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                report['cleanup_termination'] = 'owned_gateway_terminate'
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    report['cleanup_termination'] = 'owned_gateway_kill'
                    process.kill()
                    process.wait(timeout=10)
            report['owned_gateway_exit_code'] = process.returncode
        save(report)
        print(json.dumps({'phase': 'finished', 'status': report['status']}), flush=True)


if __name__ == '__main__':
    main()
