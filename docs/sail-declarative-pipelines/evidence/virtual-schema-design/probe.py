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
    for declared in [False, True]:
        for read in [False, True]:
            for missing in ['none', 'first', 'last']:
                definitions = [
                    "CREATE MATERIALIZED VIEW events_int AS SELECT 1 AS id",
                    "CREATE MATERIALIZED VIEW events_str AS SELECT 'x' AS id",
                    "CREATE STREAMING TABLE merged" + (" (id INT)" if declared else ""),
                    "CREATE FLOW merged_int AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_int)",
                    "CREATE FLOW merged_str AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_str)",
                ]
                if read:
                    definitions.append("CREATE MATERIALIZED VIEW consumer AS SELECT id FROM merged")
                bad = "CREATE MATERIALIZED VIEW late AS SELECT * FROM missing_source"
                if missing == 'first': definitions.insert(0, bad)
                if missing == 'last': definitions.append(bad)
                entry = {'declared': declared, 'read': read, 'missing': missing, 'sql': ';'.join(definitions), 'events': []}
                r['cases'].append(entry)
                graph = create_dataflow_graph(s, None, None, None)
                registry = SparkConnectGraphElementRegistry(s, graph)
                try:
                    registry.register_sql(entry['sql'], Path('virtual-schema.sql'))
                    for result in start_run(s, graph, None, False, None, True, (out/'state').as_uri()):
                        if 'pipeline_event_result' in result:entry['events'].append(result['pipeline_event_result'].event.message)
                    entry['outcome'] = 'accepted'
                except Exception as error:
                    entry.update(outcome='error', error_type=type(error).__name__, condition=error.getCondition(), sql_state=error.getSqlState(), parameters=error.getMessageParameters(), message=error.getMessage().split('\n\nJVM stacktrace:')[0])
                entry['direct'] = next((line.split(': ',1)[1].replace(r['namespace']+'.','') for line in entry.get('message','').splitlines() if line.startswith('Flows with errors: ')), None)
                entry['downstream'] = next((line.split(': ',1)[1].replace(r['namespace']+'.','') for line in entry.get('message','').splitlines() if line.startswith('Flows that failed due to upstream errors: ')), None)
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
assert r['probe_completed'] and len(r['cases']) == 12
