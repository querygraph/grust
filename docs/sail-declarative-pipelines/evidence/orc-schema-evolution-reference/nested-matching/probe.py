"""Four Spark 4.2.1 ORC nested case-matching observations."""
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
    baseline = Path('/tmp/sail-sdp-orc-schema-evolution-reference/results.json')
    previous = json.loads(baseline.read_text())
    original = Path(previous['fixtures']['ambiguous_nested']['path'])
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Four nested name observations only; no Sail qualification or general Unicode/matching policy',
              'source_pin': PIN, 'baseline_results_sha256': sha(baseline), 'script_sha256': sha(Path(__file__)),
              'python_pid': os.getpid(), 'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
              'status': 'starting', 'fixtures': {}, 'cases': []}
    save(report)
    assert sha(original) == previous['fixtures']['ambiguous_nested']['sha256']
    for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
                'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
        os.environ.pop(key, None)
    os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
    os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
    session = gateway = process = None
    try:
        session = (SparkSession.builder.remote('local[1]').config('spark.ui.enabled', 'false')
                   .config('spark.driver.memory', '512m').config('spark.sql.shuffle.partitions', '1')
                   .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri())
                   .config('spark.sql.session.timeZone', 'UTC').config('spark.sql.orc.impl', 'native')
                   .config('spark.sql.caseSensitive', 'true')
                   .config('spark.sql.orc.enableVectorizedReader', 'true')
                   .config('spark.sql.orc.enableNestedColumnVectorizedReader', 'true').getOrCreate())
        gateway, java = SparkContext._gateway, SparkContext._jvm.java
        process = gateway.proc
        assert process is not None
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
        assert report['java']['default_timezone_id'] == report['java']['user_timezone_property'] == 'UTC'
        assert report['java']['format_locale'] == 'en-US'
        assert report['java']['runtime_version'] == '20.0.2+9-78'
        assert report['java']['tzdb_versions'] == ['2023c'] and report['java']['oldmapping_property'] == 'false'
        print(json.dumps({'phase': 'started', 'java': report['java']}), flush=True)
        local_original = ROOT / 'inputs' / 'original.orc'
        local_original.parent.mkdir(exist_ok=True)
        assert not local_original.exists()
        shutil.copyfile(original, local_original)
        reverse_sql = "SELECT named_struct('bar', 22, 'Bar', 11) AS st"
        reverse = session.sql(reverse_sql)
        reverse_dir = ROOT / 'data' / 'reverse'
        reverse.coalesce(1).write.mode('error').orc(str(reverse_dir))
        reverse_files = list(reverse_dir.glob('*.orc'))
        assert len(reverse_files) == 1
        paths = {'original': local_original, 'reverse': reverse_files[0]}
        for name, path in paths.items():
            report['fixtures'][name] = {'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size,
                                         'physical_arrow': arrow_result(orc.ORCFile(path).read())}
        report['fixtures']['original']['original_path'] = str(original)
        report['fixtures']['original']['original_sha256'] = sha(original)
        report['fixtures']['reverse']['source_sql'] = reverse_sql
        report['fixtures']['reverse']['source_schema'] = reverse.schema.jsonValue()
        session.conf.set('spark.sql.caseSensitive', 'false')
        report['config'] = {n: session.conf.get(n) for n in [
            'spark.sql.session.timeZone', 'spark.sql.caseSensitive', 'spark.sql.orc.impl',
            'spark.sql.orc.enableVectorizedReader', 'spark.sql.orc.enableNestedColumnVectorizedReader',
            'spark.sql.ansi.enabled', 'spark.sql.timeType.enabled']}
        report['status'] = 'probing'
        save(report)
        for fixture, requested in [('original', 'BAR'), ('original', 'Bar'), ('reverse', 'bar'), ('reverse', 'BAR')]:
            schema = T.StructType([T.StructField('st', T.StructType([T.StructField(requested, T.IntegerType())]))])
            result = {'fixture': fixture, 'requested_name': requested, 'requested_schema': schema.jsonValue(),
                      'stage': 'construct', 'status': 'running'}
            report['cases'].append(result)
            try:
                frame = session.read.schema(schema).orc(str(paths[fixture]))
                result['stage'] = 'schema'
                result['read_schema'] = frame.schema.jsonValue()
                result['stage'] = 'explain'
                plan = io.StringIO()
                with redirect_stdout(plan): frame.explain(mode='formatted')
                result['physical_plan'] = plan.getvalue()
                result['stage'] = 'materialize_to_arrow'
                result['arrow'] = arrow_result(frame.toArrow())
                result['status'] = 'success'
            except Exception as error:
                result['status'] = 'error'
                result['error'] = error_record(error)
            save(report)
            print(json.dumps({'phase': 'case', 'fixture': fixture, 'requested': requested,
                              'status': result['status'], 'stage': result['stage']}), flush=True)
        for name, path in paths.items(): assert sha(path) == report['fixtures'][name]['sha256']
        assert sha(original) == previous['fixtures']['ambiguous_nested']['sha256']
        assert sha(baseline) == report['baseline_results_sha256']
        assert len(report['cases']) == 4
        report['status'] = 'completed'
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        if session is not None: session.stop()
        if gateway is not None: gateway.shutdown()
        if process is not None:
            if process.stdin is not None: process.stdin.close()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            report['owned_gateway_exit_code'] = process.returncode
        save(report)
        print(json.dumps({'phase': 'finished', 'status': report['status']}), flush=True)


if __name__ == '__main__':
    main()
