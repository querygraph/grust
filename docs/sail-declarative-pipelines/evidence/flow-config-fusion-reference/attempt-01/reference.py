"""Observe public Spark Connect graph configuration phases without selecting expectations."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'

from pyspark.sql import SparkSession
from pyspark.sql.connect import proto as pb
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run

KEY = 'spark.sql.caseSensitive'
SOURCE = Path('/Users/alexy/src/spark-sdp-4.2.1')
OUTPUT = Path(sys.argv[1])
OUTPUT.mkdir(exist_ok=False)
probe = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:15002', '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
assert probe.returncode == 1 and not probe.stdout, 'reference port already owned'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def define(spark, graph: str, name: str, sql: str, conf: dict[str, str], table: bool = False) -> None:
    output = pb.Command()
    output.pipeline_command.define_output.CopyFrom(pb.PipelineCommand.DefineOutput(
        dataflow_graph_id=graph, output_name=name,
        output_type=pb.OutputType.MATERIALIZED_VIEW if table else pb.OutputType.TEMPORARY_VIEW,
        table_details=pb.PipelineCommand.DefineOutput.TableDetails(format='parquet') if table else None,
    ))
    spark.client.execute_command(output)
    relation = pb.Relation()
    relation.sql.query = sql
    command = pb.Command()
    command.pipeline_command.define_flow.CopyFrom(pb.PipelineCommand.DefineFlow(
        dataflow_graph_id=graph, flow_name=name, target_dataset_name=name, sql_conf=conf,
        relation_flow_details=pb.PipelineCommand.DefineFlow.WriteRelationFlowDetails(relation=relation),
    ))
    spark.client.execute_command(command)


# Reverse lexical names make SQL encounter order distinguishable from sorted dependency order.
CASES = [
    ('upstream_true', [('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False)],
     'SELECT Foo FROM z_sensitive', {}),
    ('upstream_false_over_consumer_true', [('a_insensitive', 'SELECT 1 AS foo', {KEY: 'false'}, False)],
     'SELECT Foo FROM a_insensitive', {KEY: 'true'}),
    ('left_true_right_false', [
        ('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False),
        ('a_insensitive', 'SELECT 2 AS bar', {KEY: 'false'}, False)],
     'SELECT Foo FROM z_sensitive CROSS JOIN a_insensitive', {}),
    ('left_false_right_true', [
        ('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False),
        ('a_insensitive', 'SELECT 2 AS bar', {KEY: 'false'}, False)],
     'SELECT Foo FROM a_insensitive CROSS JOIN z_sensitive', {}),
    ('repeated_last_true', [
        ('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False),
        ('a_insensitive', 'SELECT 2 AS bar', {KEY: 'false'}, False)],
     'SELECT z1.Foo FROM z_sensitive z1 CROSS JOIN a_insensitive CROSS JOIN z_sensitive z2', {}),
    ('transitive_raw_conf', [
        ('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False),
        ('middle', 'SELECT foo FROM z_sensitive', {}, False)],
     'SELECT Foo FROM middle', {}),
    ('table_boundary', [('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, True)],
     'SELECT Foo FROM z_sensitive', {}),
    ('external_read_after_true', [('z_sensitive', 'SELECT 1 AS foo', {KEY: 'true'}, False)],
     'SELECT ext.Foo FROM z_sensitive CROSS JOIN external_input ext', {}),
]

report = {
    'started_at': datetime.now(timezone.utc).isoformat(),
    'source_commit': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
    'harness_sha256': digest(Path(__file__)),
    'scope': 'Public Connect graph observations; source pin and installed runtime are recorded separately; no Scala suite verdict',
    'cases': [],
}
spark = None
try:
    spark = (SparkSession.builder.remote('local[2]').appName('SDP config fusion reference')
             .config('spark.ui.enabled', 'false')
             .config('spark.sql.warehouse.dir', (OUTPUT / 'warehouse').as_uri()).getOrCreate())
    report['spark_version'] = spark.version
    assert spark.version == '4.2.1'
    import pyspark
    jars = Path(pyspark.__file__).parent / 'jars'
    report['runtime_jars'] = {p.name: digest(p) for p in jars.glob('spark-*4.2.1.jar') if any(x in p.name for x in ('pipelines', 'sql_', 'connect_'))}
    for name, definitions, query, conf in CASES:
        case = {'name': name, 'definitions': definitions, 'query': query, 'consumer_conf': conf}
        report['cases'].append(case)
        namespace = 'fusion_' + name
        try:
            spark.conf.set(KEY, 'false')
            spark.sql(f'CREATE DATABASE {namespace}').collect()
            spark.sql(f'USE {namespace}').collect()
            spark.sql('CREATE TABLE external_input USING parquet AS SELECT 9 AS foo').collect()
            graph = create_dataflow_graph(spark, 'spark_catalog', namespace, None)
            for definition in definitions:
                define(spark, graph, *definition)
            define(spark, graph, 'result', query, conf, table=True)
            case['events'] = []
            try:
                for event in start_run(spark, graph, None, False, None, False, (OUTPUT/name/'state').as_uri()):
                    if 'pipeline_event_result' in event:
                        e = event['pipeline_event_result'].event
                        case['events'].append({'message': e.message, 'level': str(e.level)})
                case['run_returned'] = True
            except Exception as error:
                case['run_returned'] = False
                case['run_error'] = str(error)
                case['run_exception_type'] = type(error).__name__
            case['result_exists'] = spark.catalog.tableExists('result')
            if case['result_exists']:
                case['rows'] = [row.asDict() for row in spark.table('result').collect()]
            case['session_case_sensitive'] = spark.conf.get(KEY)
        except Exception:
            case['probe_error'] = traceback.format_exc()
        print(json.dumps({k:v for k,v in case.items() if k not in ('events','definitions','run_error')}), flush=True)
    report['outcome'] = 'observed' if not any('probe_error' in c for c in report['cases']) else 'probe_error'
finally:
    if spark is not None:
        spark.stop()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (OUTPUT / 'observations.json').write_text(json.dumps(report, indent=2) + '\n')
print('Reference observations recorded', flush=True)
