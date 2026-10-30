"""Invoke ten frozen public tests through one owned local Spark Connect JVM."""
from datetime import datetime, timezone
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
REPO = Path('/Users/alexy/src/sail-pipelines-proposal')
SOURCE = REPO / 'python/pysail/tests/spark/datasource/test_orc.py'
EXPECTED_SHA = 'c8e73063a7aeb9085b7e801ac67561747cb67d545f60974d092f9f982e879f2c'
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
CURRENT = None
REPORT = {'status': 'starting', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
          'python_pid': os.getpid(), 'python_executable': sys.executable,
          'route': 'Spark Connect session via builder.remote(local[1]); direct invocation of unchanged public test functions and original fixture, not pytest runner',
          'spark_source_pin': PIN, 'source_build_provenance_claim': False,
          'cases': [], 'instrumentation': 'Observe original Connect DataFrame schema/collect/count/toArrow returns and SQL calls without adding query actions or replacing results.'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save():
    (ROOT / 'results.json').write_text(json.dumps(REPORT, indent=2, sort_keys=True, default=str) + '\n')

def error_record(error):
    try:
        condition = error.getCondition()
    except (AttributeError, TypeError):
        condition = None
    return {'python_type': type(error).__name__, 'condition': condition,
            'message': str(error), 'traceback': traceback.format_exc()}

def event(operation, **value):
    if CURRENT is not None:
        CURRENT['events'].append({'operation': operation, **value})

def arrow_result(table):
    columns = []
    for index, field in enumerate(table.schema):
        array = table.column(index)
        item = {'name': field.name, 'type': str(field.type), 'nullable': field.nullable,
                'metadata': {str(k): str(v) for k, v in (field.metadata or {}).items()},
                'values': array.to_pylist()}
        if pa.types.is_time64(field.type):
            item['nanosecond_values'] = array.cast(pa.int64()).to_pylist()
        columns.append(item)
    return {'schema': str(table.schema), 'num_rows': table.num_rows, 'columns': columns}

def timeout(_signal, _frame):
    raise TimeoutError('bounded public Spark reference exceeded 600 seconds')

for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
            'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / 'spark-local')
import pyarrow as pa
import pyspark
from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.session import SparkSession as ConnectSession

SETTINGS = ['spark.sql.session.timeZone', 'spark.sql.orc.impl', 'spark.sql.caseSensitive',
            'spark.sql.orc.enableVectorizedReader', 'spark.sql.orc.enableNestedColumnVectorizedReader',
            'spark.sql.orc.mergeSchema', 'spark.sql.orc.filterPushdown', 'spark.sql.ansi.enabled',
            'spark.sql.timestampType', 'spark.sql.timeType.enabled', 'spark.sql.shuffle.partitions',
            'spark.sql.files.ignoreCorruptFiles', 'spark.sql.files.ignoreMissingFiles',
            'spark.sql.sources.partitionColumnTypeInference.enabled', 'spark.sql.sources.useV1SourceList']

def settings(session):
    result = {key: session.conf.get(key) for key in SETTINGS}
    result['orc.force.positional.evolution'] = session.conf.get('orc.force.positional.evolution', None)
    return result

session = gateway = process = None
originals = {}
signal.signal(signal.SIGALRM, timeout)
signal.alarm(600)
save()
try:
    assert sha(SOURCE) == EXPECTED_SHA, 'public source changed after freeze'
    source_dir = ROOT / 'source'
    source_dir.mkdir()
    shutil.copyfile(SOURCE, source_dir / 'test_orc.py')
    shutil.copytree(SOURCE.parent / 'orc_data', source_dir / 'orc_data')
    REPORT['source_files'] = [{'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'size': path.stat().st_size}
                              for path in sorted(source_dir.rglob('*')) if path.is_file()]
    spec = importlib.util.spec_from_file_location('frozen_orc_public_tests', source_dir / 'test_orc.py')
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    import pysail.testing.spark.utils.sql as sql_helpers
    helper = Path(sql_helpers.__file__)
    REPORT['sql_helper'] = {'path': str(helper), 'sha256': sha(helper)}
    shutil.copyfile(helper, source_dir / 'sql_helpers.py')
    REPORT['run_sha256'] = sha(Path(__file__))
    REPORT['pyspark_version'] = pyspark.__version__
    REPORT['pyarrow_version'] = pa.__version__
    REPORT['java_tool_options'] = os.environ.get('JAVA_TOOL_OPTIONS')
    REPORT['java_home'] = os.environ.get('JAVA_HOME')
    jars = Path(pyspark.__file__).parent / 'jars'
    REPORT['runtime_jars'] = [{'name': path.name, 'sha256': sha(path), 'size': path.stat().st_size}
                              for pattern in ['spark-sql_*.jar', 'spark-sql-api_*.jar', 'spark-connect_*.jar', 'orc-core-*.jar']
                              for path in sorted(jars.glob(pattern))]
    save()
    session = (SparkSession.builder.remote('local[1]')
               .config('spark.ui.enabled', 'false').config('spark.driver.memory', '512m')
               .config('spark.sql.shuffle.partitions', '1')
               .config('spark.sql.warehouse.dir', (ROOT / 'warehouse').as_uri())
               .config('spark.sql.session.timeZone', 'UTC')
               .config('spark.sql.orc.impl', 'native')
               .getOrCreate())
    gateway, java = SparkContext._gateway, SparkContext._jvm.java
    process = gateway.proc
    assert process is not None, 'must own the gateway JVM'
    runtime = java.lang.management.ManagementFactory.getRuntimeMXBean()
    REPORT['java'] = {'gateway_pid': process.pid, 'actual_pid': int(runtime.getPid()),
                      'start_time_millis': int(runtime.getStartTime()),
                      'runtime_version': java.lang.System.getProperty('java.runtime.version'),
                      'vendor': java.lang.System.getProperty('java.vendor'),
                      'default_timezone': java.util.TimeZone.getDefault().getID(),
                      'format_locale': java.util.Locale.getDefault(java.util.Locale.Category.FORMAT).toLanguageTag(),
                      'oldmapping': java.lang.System.getProperty('sun.timezone.ids.oldmapping'),
                      'tzdb_versions': list(java.time.zone.ZoneRulesProvider.getVersions('UTC').keySet())}
    REPORT['session_class'] = f'{type(session).__module__}.{type(session).__qualname__}'
    assert isinstance(session, ConnectSession)
    REPORT['spark_version'] = session.version
    assert session.version == pyspark.__version__ == '4.2.1'
    assert REPORT['java']['actual_pid'] == process.pid
    assert REPORT['java']['runtime_version'] == '20.0.2+9-78'
    assert REPORT['java']['default_timezone'] == 'UTC'
    java_conf = SparkContext._jvm.org.apache.spark.SparkEnv.get().conf()
    REPORT['spark_context'] = {'master': java_conf.get('spark.master'), 'driver_memory': java_conf.get('spark.driver.memory')}
    assert REPORT['spark_context'] == {'master': 'local[1]', 'driver_memory': '512m'}
    REPORT['owned_process_observation'] = subprocess.check_output(['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,lstart=,command='], text=True)
    (ROOT / 'owned-jvm.pid').write_text(str(process.pid) + '\n')
    REPORT['initial_config'] = settings(session)
    assert REPORT['initial_config']['orc.force.positional.evolution'] in [None, 'false']
    print(json.dumps({'phase': 'started', 'python_pid': os.getpid(), 'java': REPORT['java'], 'session_class': REPORT['session_class']}), flush=True)
    save()

    originals['schema'] = DataFrame.schema
    def schema(self):
        result = originals['schema'].fget(self)
        event('schema', frame_id=id(self), schema=result.jsonValue())
        return result
    DataFrame.schema = property(schema, doc=originals['schema'].__doc__)
    for name in ['collect', 'count', 'toArrow']:
        original = getattr(DataFrame, name)
        originals[name] = original
        def make_wrapper(name, original):
            @wraps(original)
            def wrapper(self, *args, **kwargs):
                try:
                    result = original(self, *args, **kwargs)
                    if name == 'collect':
                        value = {'rows': [row.asDict(recursive=True) for row in result], 'repr': repr(result)}
                    elif name == 'toArrow':
                        value = arrow_result(result)
                    else:
                        value = {'count': result}
                    event(name, frame_id=id(self), result=value)
                    return result
                except Exception as error:
                    event(name, frame_id=id(self), error=error_record(error))
                    raise
            return wrapper
        setattr(DataFrame, name, make_wrapper(name, original))
    originals['sql'] = ConnectSession.sql
    @wraps(originals['sql'])
    def sql(self, query, *args, **kwargs):
        event('sql', query=query)
        return originals['sql'](self, query, *args, **kwargs)
    ConnectSession.sql = sql

    cases = [
        ('dataframe_sql', tests.test_orc_dataframe_and_sql_path_read, {}),
        ('external_catalog', tests.test_orc_external_catalog_table_reads_existing_files, {}),
        ('eleventh_file_merge', tests.test_orc_merge_schema_includes_the_eleventh_file, {}),
    ]
    for requested in ['alias', 'omitted', 'empty']:
        for sensitive in [False, True]:
            cases.append((f'partition_{requested}_case_{str(sensitive).lower()}',
                          tests.test_orc_supplied_schema_retains_discovered_partitions,
                          {'requested': requested, 'case_sensitive': sensitive}))
    cases.append(('time_precision', tests.test_orc_time_schema_and_requested_precision_preserve_stored_nanoseconds, None))
    assert len(cases) == 10
    for name, function, kwargs in cases:
        CURRENT = {'name': name, 'function': function.__name__, 'parameters': kwargs or {}, 'status': 'running', 'events': []}
        REPORT['cases'].append(CURRENT)
        directory = ROOT / 'inputs' / name
        directory.mkdir(parents=True)
        fixture = tests.orc_spark.__wrapped__(session)
        fixture_started = False
        try:
            configured = next(fixture)
            fixture_started = True
            CURRENT['config'] = settings(configured)
            if kwargs is None:
                function(configured)
            else:
                function(configured, directory, **kwargs)
            CURRENT['status'] = 'passed'
        except Exception as error:
            CURRENT['status'] = 'failed'
            CURRENT['error'] = error_record(error)
        finally:
            if fixture_started:
                try:
                    next(fixture)
                    raise AssertionError('fixture unexpectedly yielded twice')
                except StopIteration:
                    pass
                except Exception as error:
                    CURRENT['fixture_cleanup_error'] = error_record(error)
                    CURRENT['status'] = 'failed'
            CURRENT['config_after_restore'] = settings(session)
            CURRENT['created_files'] = [{'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'size': path.stat().st_size}
                                        for path in sorted(directory.rglob('*')) if path.is_file()]
            print(json.dumps({'phase': 'case', 'name': name, 'status': CURRENT['status'], 'observations': len(CURRENT['events'])}), flush=True)
            CURRENT = None
            save()
    REPORT['summary'] = {status: sum(case['status'] == status for case in REPORT['cases']) for status in ['passed', 'failed']}
    REPORT['status'] = 'completed' if REPORT['summary']['failed'] == 0 else 'completed_with_failures'
except BaseException as error:
    REPORT['status'] = 'harness_failed'
    REPORT['harness_error'] = error_record(error)
    raise
finally:
    signal.alarm(0)
    CURRENT = None
    if 'schema' in originals:
        for name in ['schema', 'collect', 'count', 'toArrow']:
            setattr(DataFrame, name, originals[name])
        ConnectSession.sql = originals['sql']
    gateway = gateway or SparkContext._gateway
    process = process or (gateway.proc if gateway is not None else None)
    for name, action in [('session_stop', lambda: session.stop() if session is not None else None),
                         ('gateway_shutdown', lambda: gateway.shutdown() if gateway is not None else None)]:
        try:
            action()
        except Exception:
            REPORT.setdefault('cleanup_errors', {})[name] = traceback.format_exc()
    if process is not None:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                REPORT.setdefault('cleanup_errors', {})['stdin_close'] = traceback.format_exc()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            REPORT['cleanup_termination'] = 'owned_gateway_terminate'
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                REPORT['cleanup_termination'] = 'owned_gateway_kill'
                process.kill()
                process.wait(timeout=15)
        REPORT['owned_gateway_exit_code'] = process.returncode
        check = subprocess.run(['ps', '-p', str(process.pid), '-o', 'pid=,ppid=,lstart=,command='], text=True, capture_output=True)
        REPORT['terminal_pid_check'] = {'pid': process.pid, 'exit_code': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr}
    REPORT['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'phase': 'finished', 'status': REPORT['status'], 'summary': REPORT.get('summary'), 'jvm_exit': REPORT.get('owned_gateway_exit_code')}), flush=True)
