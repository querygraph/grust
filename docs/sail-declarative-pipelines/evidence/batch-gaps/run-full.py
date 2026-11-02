"""usage: run-full.py OUT BINARY ROOT PORT nodes...; the whole-tree harness: the server sees pysail and the optional
test dependencies, shares the tests' working directory, and pytest runs with the same paths."""
import os, signal, socket, subprocess, sys, time
from pathlib import Path
out=Path(sys.argv[1]); binary, root, port = sys.argv[2], sys.argv[3], int(sys.argv[4]); nodes=sys.argv[5:]
out.mkdir(exist_ok=False); venv='/Users/alexy/src/sail-pipelines-proposal/.venv'; deps=str(Path(__file__).resolve().parent.parent/'pydeps')
def bound():
    with socket.socket() as c:
        c.settimeout(.2); return c.connect_ex(('127.0.0.1',port))==0
assert not bound()
java=subprocess.check_output(['/usr/libexec/java_home','-v','17'],text=True).strip()
path=os.pathsep.join([root+'/python',deps,venv+'/lib/python3.12/site-packages'])
base={**os.environ,'SAIL_EXECUTION__DEFAULT_PARALLELISM':'4','SAIL_RUNTIME__STACK_SIZE':'16777216','JAVA_HOME':java,'PYTHONPATH':path,'VIRTUAL_ENV':venv,'PATH':venv+'/bin:'+os.environ['PATH'],'PYSPARK_PYTHON':venv+'/bin/python'}
with (out/'server.log').open('w') as log:
    p=subprocess.Popen([binary,'spark','server','--port',str(port)],cwd=root,env=base,stdout=log,stderr=subprocess.STDOUT)
try:
    t=time.monotonic()
    while not bound():
        assert p.poll() is None and time.monotonic()-t<60; time.sleep(.1)
    env={**base,'SPARK_REMOTE':f'sc://localhost:{port}'}
    r=subprocess.run([sys.executable,'-m','pytest',*nodes,'-q','--no-header','--tb=line','-p','no:cacheprovider','--junitxml='+str(out/'pytest.xml')],cwd=root,env=env,capture_output=True,text=True)
    (out/'pytest.log').write_text(r.stdout+r.stderr); print(r.stdout[-1500:]); print('exit',r.returncode)
finally:
    p.send_signal(signal.SIGINT)
    try: p.wait(30)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(15)
print('listening_after',bound())
