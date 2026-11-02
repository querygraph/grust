"""usage: sail-public.py OUT [pytest nodes]; runs against the gate CLI on port 50095."""
import json, os, signal, socket, subprocess, sys, time
from pathlib import Path
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
nodes=sys.argv[2:] or ['python/pysail/tests/spark/pipelines/test_streaming_input_schema.py']
root=os.environ.get('TEST_ROOT','/Users/alexy/src/sail-sdp-gate'); cli='/Users/alexy/src/sail-sdp-gate'; venv='/Users/alexy/src/sail-pipelines-proposal/.venv'
def bound():
    with socket.socket() as c:
        c.settimeout(.2); return c.connect_ex(('127.0.0.1',50095))==0
assert not bound()
base={**os.environ,'VIRTUAL_ENV':venv,'PYTHONPATH':venv+'/lib/python3.12/site-packages'}
base.pop('SPARK_REMOTE',None)
with (out/'server.log').open('w') as log:
    p=subprocess.Popen([cli+'/target/debug/sail','spark','server','--port','50095'],cwd=out,env=base,stdout=log,stderr=subprocess.STDOUT)
try:
    t=time.monotonic()
    while not bound():
        assert p.poll() is None and time.monotonic()-t<30; time.sleep(.1)
    env={**base,'PYTHONPATH':root+'/python'+os.pathsep+venv+'/lib/python3.12/site-packages','SPARK_REMOTE':'sc://localhost:50095'}
    r=subprocess.run([sys.executable,'-m','pytest',*nodes,'-q','--no-header','--tb=short','-p','no:cacheprovider','--junitxml='+str(out/'pytest.xml')],cwd=root,env=env,capture_output=True,text=True)
    (out/'pytest.log').write_text(r.stdout+r.stderr)
    print(r.stdout[-6000:]); print('exit',r.returncode)
finally:
    p.send_signal(signal.SIGINT)
    try: p.wait(30)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(15)
print('listening_after',bound())
