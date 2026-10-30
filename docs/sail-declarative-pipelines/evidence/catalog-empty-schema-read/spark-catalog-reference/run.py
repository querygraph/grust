"""One owned Spark Connect JVM: six generic catalog controls and IF NOT EXISTS."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parent
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
REPORT = {'status': 'starting', 'started_at': datetime.now(timezone.utc).isoformat(),
          'python_pid': os.getpid(), 'python_executable': sys.executable,
          'spark_source_pin': PIN, 'installed_jars_built_from_source_checkout_claim': False,
          'route': 'Spark Connect builder.remote(local[1]); one owned JVM', 'cases': []}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save():
    (ROOT / 'results.json').write_text(json.dumps(REPORT, indent=2, sort_keys=True) + '\n')


def error_record(error):
    return {'type': type(error).__name__, 'condition': error.getCondition() if hasattr(error, 'getCondition') else None,
            'message': str(error), 'traceback': traceback.format_exc()}


def timeout(_signum, _frame):
    raise TimeoutError('bounded catalog reference exceeded 600 seconds')


for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
            'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
import pyarrow as pa
from pyarrow import orc, parquet
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.connect.session import SparkSession as ConnectSession

spark = gateway = process = None
signal.signal(signal.SIGALRM, timeout)
signal.alarm(600)
save()
try:
    source_dir = ROOT / 'source'
    source_dir.mkdir()
    original = Path('/tmp/sail-sdp-orc-catalog-control.py')
    shutil.copyfile(original, source_dir / 'sail-catalog-control.py')
    REPORT['original_control'] = {'path': str(original), 'sha256': sha(original)}
    source_path = 'sql/core/src/main/scala/org/apache/spark/sql/execution/command/createDataSourceTables.scala'
    repo = '/Users/alexy/src/spark-sdp-4.2.1'
    data = subprocess.check_output(['git', '-C', repo, 'show', PIN + ':' + source_path])
    (source_dir / 'createDataSourceTables.scala').write_bytes(data)
    REPORT['source_anchor'] = {'repository': repo, 'commit': PIN, 'path': source_path,
        'blob': subprocess.check_output(['git', '-C', repo, 'rev-parse', PIN + ':' + source_path], text=True).strip(),
        'sha256': hashlib.sha256(data).hexdigest(), 'relevant_lines': [[49, 86], [99, 126]]}
    REPORT['script_sha256'] = sha(Path(__file__))
    REPORT['java_home'] = os.environ['JAVA_HOME']
    REPORT['java_tool_options'] = os.environ['JAVA_TOOL_OPTIONS']
    REPORT['pyspark_version'], REPORT['pyarrow_version'] = pyspark.__version__, pa.__version__
    jars = Path(pyspark.__file__).parent / 'jars'
    REPORT['runtime_jars'] = [{'name': path.name, 'sha256': sha(path), 'size': path.stat().st_size}
                             for pattern in ['spark-sql_*.jar', 'spark-sql-api_*.jar', 'spark-connect_*.jar', 'orc-core-*.jar']
                             for path in sorted(jars.glob(pattern))]
    inputs = ROOT / 'inputs'
    inputs.mkdir()
    for fmt in ['orc', 'parquet', 'json']:
        directory = inputs / fmt
        directory.mkdir()
        path = directory / ('part.' + fmt)
        table = pa.table({'id': pa.array([3, 1], type=pa.int32())})
        if fmt == 'orc':
            orc.write_table(table, path)
        elif fmt == 'parquet':
            parquet.write_table(table, path)
        else:
            path.write_text('{"id":3}\n{"id":1}\n')
    REPORT['inputs_before'] = [{'path': str(path.relative_to(ROOT)), 'size': path.stat().st_size, 'sha256': sha(path)}
                               for path in sorted(inputs.rglob('*')) if path.is_file()]
    save()
    spark = (SparkSession.builder.remote('local[1]').config('spark.ui.enabled', 'false')
             .config('spark.driver.memory', '512m').config('spark.sql.shuffle.partitions', '1')
             .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri())
             .config('spark.sql.session.timeZone', 'UTC').config('spark.sql.orc.impl', 'native').getOrCreate())
    gateway, java = SparkContext._gateway, SparkContext._jvm.java
    process = gateway.proc
    assert process is not None
    runtime = java.lang.management.ManagementFactory.getRuntimeMXBean()
    REPORT['java'] = {'gateway_pid': process.pid, 'actual_pid': int(runtime.getPid()),
                     'start_time_millis': int(runtime.getStartTime()),
                     'version': java.lang.System.getProperty('java.runtime.version'),
                     'default_timezone': java.util.TimeZone.getDefault().getID(),
                     'format_locale': java.util.Locale.getDefault(java.util.Locale.Category.FORMAT).toLanguageTag(),
                     'oldmapping': java.lang.System.getProperty('sun.timezone.ids.oldmapping')}
    REPORT['spark_version'] = spark.version
    REPORT['session_class'] = f'{type(spark).__module__}.{type(spark).__qualname__}'
    assert isinstance(spark, ConnectSession) and spark.version == pyspark.__version__ == '4.2.1'
    assert REPORT['java']['actual_pid'] == process.pid and REPORT['java']['version'] == '20.0.2+9-78'
    assert REPORT['java']['default_timezone'] == 'UTC'
    conf = SparkContext._jvm.org.apache.spark.SparkEnv.get().conf()
    REPORT['spark_context'] = {'master': conf.get('spark.master'), 'driver_memory': conf.get('spark.driver.memory')}
    assert REPORT['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
    REPORT['config'] = {key: spark.conf.get(key) for key in [
        'spark.sql.orc.impl', 'spark.sql.orc.mergeSchema', 'spark.sql.caseSensitive',
        'spark.sql.session.timeZone', 'spark.sql.ansi.enabled', 'spark.sql.timeType.enabled',
        'spark.sql.sources.useV1SourceList', 'spark.sql.catalogImplementation',
        'spark.sql.orc.enableVectorizedReader', 'spark.sql.files.ignoreCorruptFiles',
        'spark.sql.files.ignoreMissingFiles', 'spark.sql.sources.partitionColumnTypeInference.enabled']}
    REPORT['config']['orc.force.positional.evolution'] = spark.conf.get('orc.force.positional.evolution', None)
    REPORT['owned_process'] = subprocess.check_output(['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,lstart=,command='], text=True)
    (ROOT / 'owned-jvm.pid').write_text(str(process.pid) + '\n')
    print(json.dumps({'phase': 'started', 'python_pid': os.getpid(), 'jvm_pid': process.pid}), flush=True)
    save()
    for fmt in ['orc', 'parquet', 'json']:
        directory = inputs / fmt
        path = directory / ('part.' + fmt)
        for explicit in [False, True]:
            name = 'orc_control_' + uuid.uuid4().hex
            query = f"CREATE TABLE {name} {'(id INT)' if explicit else ''} USING {fmt} LOCATION '{directory}'"
            case = {'format': fmt, 'explicit_schema': explicit, 'query': query, 'status': 'running'}
            REPORT['cases'].append(case)
            before = sha(path)
            try:
                direct = spark.read.format(fmt).load(str(directory))
                case['direct_schema'] = direct.schema.jsonValue()
                case['direct_rows'] = [list(row) for row in direct.collect()]
                spark.sql(query)
                frame = spark.table(name)
                case['table_schema'] = frame.schema.jsonValue()
                case['table_rows'] = [list(row) for row in frame.collect()]
                case['describe'] = [list(row) for row in spark.sql('DESCRIBE TABLE ' + name).collect()]
                case['status'] = 'succeeded'
            except Exception as error:
                case['status'] = 'error'
                case['error'] = error_record(error)
            finally:
                spark.sql('DROP TABLE IF EXISTS ' + name)
                case['file_unchanged'] = before == sha(path)
                save()
            print(json.dumps({'phase': 'case', 'format': fmt, 'explicit_schema': explicit, 'status': case['status']}), flush=True)
    name, control_name = 'orc_exists_' + uuid.uuid4().hex, 'orc_missing_' + uuid.uuid4().hex
    missing = ROOT / 'missing-location'
    assert not missing.exists()
    directory = inputs / 'orc'
    case = {'name': 'existing_if_not_exists_missing_location', 'format': 'orc', 'status': 'running',
            'missing_path_before': missing.exists(), 'missing_path': str(missing)}
    REPORT['cases'].append(case)
    try:
        spark.sql(f"CREATE TABLE {name} USING orc LOCATION '{directory}'")
        before = spark.table(name)
        case['schema_before'] = before.schema.jsonValue()
        case['rows_before'] = [list(row) for row in before.collect()]
        case['describe_before'] = [list(row) for row in spark.sql('DESCRIBE EXTENDED ' + name).collect()]
        case['query'] = f"CREATE TABLE IF NOT EXISTS {name} USING orc LOCATION '{missing}'"
        spark.sql(case['query'])
        after = spark.table(name)
        case['schema_after'] = after.schema.jsonValue()
        case['rows_after'] = [list(row) for row in after.collect()]
        case['describe_after'] = [list(row) for row in spark.sql('DESCRIBE EXTENDED ' + name).collect()]
        case['existing_table_unchanged'] = all(case[key + '_before'] == case[key + '_after'] for key in ['schema', 'rows', 'describe'])
        case['missing_path_after'] = missing.exists()
        case['missing_new_table_control'] = {'query': f"CREATE TABLE {control_name} USING orc LOCATION '{missing}'"}
        try:
            spark.sql(case['missing_new_table_control']['query'])
            case['missing_new_table_control']['outcome'] = 'succeeded'
        except Exception as error:
            case['missing_new_table_control']['outcome'] = 'error'
            case['missing_new_table_control']['error'] = error_record(error)
        case['control_table_exists'] = spark.catalog.tableExists(control_name)
        case['status'] = 'succeeded'
    except Exception as error:
        case['status'] = 'error'
        case['error'] = error_record(error)
    finally:
        spark.sql('DROP TABLE IF EXISTS ' + name)
        spark.sql('DROP TABLE IF EXISTS ' + control_name)
        save()
    print(json.dumps({'phase': 'case', 'name': case['name'], 'status': case['status']}), flush=True)
    REPORT['inputs_after'] = [{'path': str(path.relative_to(ROOT)), 'size': path.stat().st_size, 'sha256': sha(path)}
                              for path in sorted(inputs.rglob('*')) if path.is_file()]
    REPORT['all_input_files_unchanged'] = REPORT['inputs_before'] == REPORT['inputs_after']
    REPORT['summary'] = {key: sum(case['status'] == key for case in REPORT['cases']) for key in ['succeeded', 'error']}
    REPORT['status'] = 'completed'
except BaseException as error:
    REPORT['status'] = 'harness_failed'
    REPORT['harness_error'] = error_record(error)
    raise
finally:
    signal.alarm(0)
    gateway = gateway or SparkContext._gateway
    process = process or (gateway.proc if gateway is not None else None)
    for label, action in [('session_stop', lambda: spark.stop() if spark is not None else None),
                          ('gateway_shutdown', lambda: gateway.shutdown() if gateway is not None else None)]:
        try:
            action()
        except Exception:
            REPORT.setdefault('cleanup_errors', {})[label] = traceback.format_exc()
    if process is not None:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            REPORT['cleanup_escalation'] = 'owned gateway terminate'
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                REPORT['cleanup_escalation'] = 'owned gateway kill'
                process.kill()
                process.wait(timeout=15)
        REPORT['owned_gateway_exit_code'] = process.returncode
        check = subprocess.run(['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,lstart=,command='], text=True, capture_output=True)
        REPORT['terminal_pid_check'] = {'pid': process.pid, 'exit_code': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr}
    REPORT['completed_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'phase': 'finished', 'status': REPORT['status'], 'summary': REPORT.get('summary'), 'jvm_exit': REPORT.get('owned_gateway_exit_code')}), flush=True)
