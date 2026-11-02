from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, signal, subprocess, sys, time
from pyspark.sql import SparkSession
mode, dest = sys.argv[1:3]
out = Path(dest); out.mkdir(exist_ok=False)
root = Path('/Users/alexy/src/sail-sdp-gate')
cli = root / 'target/debug/sail'
port = 15002 if mode == 'spark' else 50095

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def owners():
    p = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
    assert p.returncode in (0, 1)
    return sorted(int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p'))
assert not owners()
r = {'started_at': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'script_sha256': sha(__file__)}
s = process = None
try:
    if mode == 'spark':
        for k in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE']: os.environ.pop(k, None)
        os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
        s = SparkSession.builder.remote('local[2]').appName('sdp-analysis-order').config('spark.sql.warehouse.dir', (out/'warehouse').as_uri()).getOrCreate()
    else:
        receipt = json.loads(Path(sys.argv[3]).read_text())
        assert receipt['outcome'] == 'passed' and receipt['cli_sha256'] == sha(cli)
        r.update(runtime_commit=receipt['sail_commit'], cli_sha256=sha(cli))
        with (out/'server.log').open('w') as log:
            process = subprocess.Popen([str(cli), 'spark', 'server', '--port', str(port)], cwd=root, env={**os.environ, 'VIRTUAL_ENV': '/Users/alexy/src/sail-pipelines-proposal/.venv', 'PYTHONPATH': '/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while not owners():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.1)
        assert owners() == [process.pid]
        s = SparkSession.builder.remote(f'sc://localhost:{port}').create()
    r['version'] = s.version; assert s.version == '4.2.1'
    from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
    from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run
    r['namespace'] = f"{s.catalog.currentCatalog()}.{s.catalog.currentDatabase()}"
    r['cases'] = []
    s.conf.set('spark.sql.timeType.enabled', 'true')
    from pyspark.pipelines.add_pipeline_analysis_context import add_pipeline_analysis_context
    for expression in [
        'CAST(NULL AS TIME(3))',
        'CAST(NULL AS TIME(6))',
        "CAST('12:34:56.123' AS TIME(3))",
        "CAST('12:34:56.123' AS TIME(6))",
        'CAST(NULL AS INTERVAL YEAR)',
        'CAST(NULL AS INTERVAL MONTH)',
        'CAST(NULL AS INTERVAL DAY)',
        'CAST(NULL AS INTERVAL HOUR TO MINUTE)',
        'CAST(NULL AS ARRAY<TIME(3)>)',
        'CAST(NULL AS STRUCT<x:TIME(3)>)',
        'CAST(NULL AS ARRAY<INTERVAL YEAR>)',
    ]:
        entry = {'expression': expression, 'observations': []}
        r['cases'].append(entry)
        query = 'SELECT '+expression+' AS id'
        direct = s.sql(query)
        entry['direct_schema'] = direct.schema.jsonValue()
        entry['direct_typeof'] = direct.selectExpr('typeof(id) AS type').first()['type']
        if 'TIME' in expression:
            entry['direct_explain'] = '\n'.join(row[0] for row in s.sql('EXPLAIN EXTENDED '+query).collect())
        for source_kind in ['MATERIALIZED VIEW', 'TEMPORARY VIEW']:
            graph = create_dataflow_graph(s, None, None, None)
            registry = SparkConnectGraphElementRegistry(s, graph)
            registry.register_sql('CREATE '+source_kind+' source AS '+query+';CREATE MATERIALIZED VIEW consumer AS SELECT * FROM source', Path('schema-boundary.sql'))
            for streaming in [False, True]:
                observation = {'source_kind': source_kind, 'streaming': streaming}
                entry['observations'].append(observation)
                try:
                    with add_pipeline_analysis_context(spark=s, dataflow_graph_id=graph, flow_name='consumer'):
                        df = s.readStream.table('source') if streaming else s.table('source')
                        observation['schema'] = df.schema.jsonValue()
                    observation['outcome'] = 'schema'
                except Exception as error:
                    observation.update(outcome='error', error_type=type(error).__name__, message=str(error).split('\n\nJVM stacktrace:')[0])
    r['probe_completed'] = True

finally:
    if s is not None: s.stop()
    if process is not None:
        if process.poll() is None: process.send_signal(signal.SIGINT)
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=15)
        r['server_exit_code'] = process.returncode
    r.update(completed_at=datetime.now(timezone.utc).isoformat(), remaining_listeners=owners())
    (out/'observations.json').write_text(json.dumps(r, indent=2)+'\n')
assert not r['remaining_listeners']
print(json.dumps(r))
assert r['probe_completed'] and len(r['cases']) == 11
