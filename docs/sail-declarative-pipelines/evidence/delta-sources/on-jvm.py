"""usage: on-jvm.py OUT PORT pytest-nodes...; runs tests against a Spark 4.2.1 + Delta 4.4.1 Connect server."""
import os,signal,socket,subprocess,sys,time
from pathlib import Path
out=Path(sys.argv[1]); port=int(sys.argv[2]); nodes=sys.argv[3:]; out.mkdir(exist_ok=False)
J=Path(__file__).resolve().parent; V='/Users/alexy/src/sail-pipelines-proposal/.venv'; R='/Users/alexy/src/sail-pipelines-proposal'
home=V+'/lib/python3.12/site-packages/pyspark'
java=subprocess.check_output(['/usr/libexec/java_home','-v','17'],text=True).strip()
cp=f"{J}/delta-spark_4.2_2.13-4.4.1.jar:{J}/delta-storage-4.4.1.jar"
env={**os.environ,'JAVA_HOME':java,'SPARK_HOME':home,'SPARK_LOCAL_IP':'127.0.0.1'}
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: env.pop(k,None)
log=(out/'server.log').open('w')
p=subprocess.Popen([home+'/bin/spark-submit','--class','org.apache.spark.sql.connect.service.SparkConnectServer','--master','local[2]',
 '--conf',f'spark.connect.grpc.binding.port={port}','--conf',f'spark.driver.extraClassPath={cp}','--conf','spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension',
 '--conf','spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog','--conf',f'spark.sql.warehouse.dir={(out/"wh").as_uri()}'],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
def up():
    with socket.socket() as c:
        c.settimeout(.2); return c.connect_ex(('127.0.0.1',port))==0
try:
    t=time.monotonic()
    while not up():
        assert p.poll() is None and time.monotonic()-t<120; time.sleep(.5)
    e={**env,'PYTHONPATH':R+'/python'+os.pathsep+V+'/lib/python3.12/site-packages','SPARK_REMOTE':f'sc://localhost:{port}'}
    r=subprocess.run([V+'/bin/python','-m','pytest',*nodes,'-q','--no-header','--tb=line','-p','no:cacheprovider','-x' if 0 else '-q'],capture_output=True,text=True,env=e,cwd=R+'/python')
    (out/'pytest.log').write_text(r.stdout+r.stderr); print(r.stdout[-2500:]); print('exit',r.returncode)
finally:
    p.terminate()
    try: p.wait(30)
    except subprocess.TimeoutExpired: p.kill()
