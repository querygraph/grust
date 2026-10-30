from pathlib import Path
import importlib.util
import json
import os
import subprocess
import traceback
from unittest.mock import patch
from uuid import uuid4

for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
probe = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:15002', '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
assert probe.returncode == 1 and not probe.stdout
from pyspark.sql import SparkSession
source = Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/pipelines/test_flow_file_config.py')
spec = importlib.util.spec_from_file_location('flow_config_probe_tests', source)
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
root = Path('/tmp/sail-sdp-flow-config-probe-' + uuid4().hex)
root.mkdir()
report = {'root': str(root), 'cases': []}
spark = None
try:
    spark = SparkSession.builder.remote('local[2]').appName('SDP ORC registration probe').config('spark.ui.enabled', 'false').getOrCreate()
    report['spark_version'] = spark.version
    assert spark.version == '4.2.1'
    fixture = tests.native_orc_pipeline_session.__wrapped__(spark)
    next(fixture)
    directory = tests.evolving_orc_files.__wrapped__(root)
    original_execute = spark.client.execute_command
    commands = []
    def capture(command, *args, **kwargs):
        if command.HasField('pipeline_command'):
            kind = command.pipeline_command.WhichOneof('command_type')
            detail = getattr(command.pipeline_command, kind)
            commands.append({'kind': kind, 'sql_conf': dict(detail.sql_conf) if hasattr(detail, 'sql_conf') else None})
        return original_execute(command, *args, **kwargs)
    for name, graph_merge, flow_merge, mode in [('graph-default', 'true', None, 'dataframe'), ('explicit-flow', 'false', 'true', 'dataframe'), ('sql-graph-default', 'true', None, 'sql'), ('named-path-graph-default', 'true', None, 'named')]:
        output = 'orc_config_probe_' + uuid4().hex
        case = {'name': name, 'commands': commands}
        commands = []
        try:
            with patch.object(spark.client, 'execute_command', side_effect=capture):
                with tests.configured_graph(spark, {tests.MERGE_SCHEMA: graph_merge}) as (graph_id, registry):
                    if mode == 'sql':
                        registry.register_sql(f'CREATE MATERIALIZED VIEW {output} USING parquet AS SELECT * FROM orc.`{directory}`', root / 'probe.sql')
                    else:
                        with tests.registration.graph_element_registration_context(registry):
                            if mode == 'named':
                                read_input = lambda: spark.read.table(f'orc.`{directory}`')
                            else:
                                read_input = lambda: spark.read.orc(str(directory))
                            tests.dp.materialized_view(name=output, spark_conf={} if flow_merge is None else {tests.MERGE_SCHEMA: flow_merge}, format='parquet')(read_input)
                    tests.run_graph(spark, graph_id, root)
                frame = spark.table(output)
                case['schema'] = frame.schema.jsonValue()
                case['rows'] = [row.asDict() for row in frame.orderBy('id').collect()]
                case['ambient_merge_schema'] = spark.conf.get(tests.MERGE_SCHEMA)
        except Exception:
            case['error'] = traceback.format_exc()
        finally:
            case['commands'] = commands
            report['cases'].append(case)
            spark.sql(f'DROP TABLE IF EXISTS {output}')
    try:
        next(fixture)
    except StopIteration:
        pass
finally:
    if spark:
        spark.stop()
    (root / 'probe.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
