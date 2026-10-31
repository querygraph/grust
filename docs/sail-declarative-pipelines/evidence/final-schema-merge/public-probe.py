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
    test_root = Path(os.environ.get('SDP_TEST_ROOT', '/Users/alexy/src/sail-pipelines-proposal' if mode == 'spark' else str(root)))
    path = os.environ.get('SDP_TEST_PATH', 'python/pysail/tests/spark/pipelines/test_analysis_order.py')
    r['test_sha256'] = sha(test_root/path)
    env = {**os.environ, 'PYTHONPATH': str(test_root/'python')+os.pathsep+'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages', 'SPARK_REMOTE': f'sc://localhost:{port}'}
    with (out/'pytest.log').open('w') as log:
        nodes = json.loads(os.environ.get('SDP_TEST_NODES', 'null')) or [path]
        r['pytest_nodes'] = nodes
        inputs = {node.split('::')[0] for node in nodes}
        inputs.update(['python/pysail/tests/spark/pipelines/features/sql.feature', 'python/pysail/tests/spark/pipelines/features/views.feature', 'python/pysail/tests/spark/pipelines/conftest.py', 'python/pysail/testing/spark/steps/pipelines.py'])
        r['source_sha256'] = {name: sha(test_root/name) for name in sorted(inputs)}
        result = subprocess.run([sys.executable, '-m', 'pytest', *nodes, '-q', '--junitxml='+str(out/'pytest.xml')], cwd=test_root, env=env, stdout=log, stderr=subprocess.STDOUT)
    r['pytest_exit_code'] = result.returncode
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
raise SystemExit(r['pytest_exit_code'])
