"""Sixteen bounded Spark 4.2.1 ORC schema-merge case observations."""
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
from pyspark.sql import SparkSession, functions as F, types as T

ROOT = Path(__file__).resolve().parent
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(report):
    (ROOT / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


def arrow_result(table):
    return {'schema': str(table.schema), 'num_rows': table.num_rows,
            'columns': [{'ordinal': i, 'name': field.name, 'type': str(field.type),
                         'nullable': field.nullable, 'values': table.column(i).to_pylist()}
                        for i, field in enumerate(table.schema)], 'rows': table.to_pylist()}


def error_record(error):
    try:
        condition = error.getCondition()
    except (AttributeError, TypeError):
        condition = None
    return {'python_type': type(error).__name__, 'condition': condition,
            'message': str(error), 'traceback': traceback.format_exc()}


def materialize(frame, receipt):
    receipt['stage'] = 'output_schema'
    receipt['output_schema'] = frame.schema.jsonValue()
    receipt['stage'] = 'explain'
    plan = io.StringIO()
    with redirect_stdout(plan):
        frame.explain(mode='formatted')
    receipt['physical_plan'] = plan.getvalue()
    receipt['stage'] = 'materialize_to_arrow'
    receipt['arrow'] = arrow_result(frame.toArrow())
    receipt['status'] = 'success'


def fixture_table(kind, name, value, ident):
    leaf = pa.struct([pa.field(name, pa.int32())])
    spark_leaf = T.StructType([T.StructField(name, T.IntegerType(), True)])
    if kind == 'root':
        field, arrow_type, spark_type, data = name, pa.int32(), T.IntegerType(), value
    elif kind == 'struct':
        field, arrow_type, spark_type, data = 's', leaf, spark_leaf, {name: value}
    elif kind == 'list':
        field, arrow_type, spark_type, data = 'items', pa.list_(leaf), T.ArrayType(spark_leaf, True), [{name: value}]
    elif kind == 'map_value':
        field, arrow_type = 'lookup', pa.map_(pa.string(), leaf)
        spark_type, data = T.MapType(T.StringType(), spark_leaf, True), [('k', {name: value})]
    else:
        raise AssertionError(kind)
    table = pa.Table.from_arrays([pa.array([ident], type=pa.int32()), pa.array([data], type=arrow_type)],
                                schema=pa.schema([pa.field('id', pa.int32()), pa.field(field, arrow_type)]))
    spark_schema = T.StructType([T.StructField('id', T.IntegerType(), True), T.StructField(field, spark_type, True)])
    return table, spark_schema.jsonValue()


def main():
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Sixteen ASCII-name native ORC file-read observations plus eight separately labelled JVM StructType.merge diagnostics. Plans are pre-execution.',
              'spark_source_pin': PIN, 'script_sha256': sha(Path(__file__)),
              'python_pid': os.getpid(), 'pyarrow_version': pa.__version__,
              'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
              'status': 'starting', 'fixtures': {}, 'cases': [], 'merge_diagnostics': []}
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
        for kind in ['root', 'struct', 'list', 'map_value']:
            (inputs / kind).mkdir()
            for spelling, filename, ident, value in [('Value', 'a_upper.orc', 11, 111), ('value', 'b_lower.orc', 22, 222)]:
                path = inputs / kind / filename
                table, spark_schema = fixture_table(kind, spelling, value, ident)
                fixture = {'kind': kind, 'field_spelling': spelling, 'generator': 'pyarrow.orc.write_table',
                           'input_arrow': arrow_result(table), 'diagnostic_schema_json': spark_schema,
                           'stage': 'write', 'status': 'running'}
                report['fixtures'][f'{kind}/{filename}'] = fixture
                try:
                    assert not path.exists()
                    orc.write_table(table, path)
                    fixture.update({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size,
                                    'stage': 'physical_read'})
                    physical = orc.ORCFile(path)
                    fixture['physical_schema'] = str(physical.schema)
                    fixture['physical_arrow'] = arrow_result(physical.read())
                    assert fixture['physical_arrow']['rows'] == fixture['input_arrow']['rows']
                    fixture['status'] = 'success'
                except Exception as error:
                    fixture['status'] = 'error'
                    fixture['error'] = error_record(error)
                    if path.exists():
                        fixture.update({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
                save(report)
                print(json.dumps({'phase': 'fixture', 'name': f'{kind}/{filename}', 'status': fixture['status']}), flush=True)
        if not all(item['status'] == 'success' for item in report['fixtures'].values()):
            report['status'] = 'fixture_unavailable'
            return
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
                          'jvm_start_time_millis': int(runtime.getStartTime()),
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
                    'spark.sql.files.ignoreCorruptFiles', 'spark.sql.files.ignoreMissingFiles',
                    'spark.sql.sources.partitionColumnTypeInference.enabled', 'spark.sql.sources.useV1SourceList']
        report['config'] = {name: session.conf.get(name) for name in settings}
        java_conf = SparkContext._jvm.org.apache.spark.SparkEnv.get().conf()
        report['spark_context'] = {'master': java_conf.get('spark.master'), 'driver_memory': java_conf.get('spark.driver.memory')}
        assert report['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
        report['owned_process_observation'] = subprocess.check_output(
            ['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,lstart=,command='], text=True)
        report['status'] = 'probing'
        save(report)
        print(json.dumps({'phase': 'started', 'java': report['java']}), flush=True)
        for sensitivity in [True, False]:
            session.conf.set('spark.sql.caseSensitive', str(sensitivity).lower())
            for kind in ['root', 'struct', 'list', 'map_value']:
                diagnostic = {'kind': kind, 'case_sensitive_argument': sensitivity,
                              'scope': 'Direct JVM StructType.merge on parsed schema JSON, not a file-read result',
                              'stage': 'parse_json', 'status': 'running'}
                report['merge_diagnostics'].append(diagnostic)
                try:
                    left_json = report['fixtures'][f'{kind}/a_upper.orc']['diagnostic_schema_json']
                    right_json = report['fixtures'][f'{kind}/b_lower.orc']['diagnostic_schema_json']
                    diagnostic.update({'left_schema': left_json, 'right_schema': right_json})
                    types = SparkContext._jvm.org.apache.spark.sql.types.DataType
                    left = types.fromJson(json.dumps(left_json))
                    right = types.fromJson(json.dumps(right_json))
                    diagnostic['stage'] = 'merge'
                    merged = left.merge(right, sensitivity)
                    diagnostic['merged_schema'] = json.loads(merged.json())
                    diagnostic['status'] = 'success'
                except Exception as error:
                    diagnostic['status'] = 'error'
                    diagnostic['error'] = error_record(error)
                save(report)
                for merge in [True, False]:
                    name = f'{kind}_case_{str(sensitivity).lower()}_merge_{str(merge).lower()}'
                    result = {'name': name, 'kind': kind, 'path': str(inputs / kind),
                              'reader_options': {'mergeSchema': str(merge).lower()},
                              'config': {key: session.conf.get(key) for key in settings},
                              'stage': 'construct', 'status': 'running'}
                    report['cases'].append(result)
                    try:
                        frame = session.read.option('mergeSchema', str(merge).lower()).orc(str(inputs / kind))
                        result['stage'] = 'read_schema'
                        result['read_schema'] = frame.schema.jsonValue()
                        materialize(frame, result)
                    except Exception as error:
                        result['status'] = 'error'
                        result['error'] = error_record(error)
                    save(report)
                    print(json.dumps({'phase': 'case', 'name': name, 'status': result['status'],
                                      'stage': result['stage']}), flush=True)
        for fixture in report['fixtures'].values():
            assert sha(Path(fixture['path'])) == fixture['sha256']
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
