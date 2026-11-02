import os, subprocess, sys
from pathlib import Path
from pyspark.sql import SparkSession
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
s=SparkSession.builder.remote('local[2]').appName('p').config('spark.sql.warehouse.dir',(out/'wh').as_uri()).getOrCreate()
root='/Users/alexy/src/sail-pipelines-proposal'
env={**os.environ,'PYTHONPATH':root+'/python'+os.pathsep+root+'/.venv/lib/python3.12/site-packages','SPARK_REMOTE':'sc://localhost:15002'}
r=subprocess.run([sys.executable,'-m','pytest','python/pysail/tests/spark/pipelines/test_streaming_input_schema.py','-q','--no-header','-x' if len(sys.argv)>2 else '-q','--tb=line'],cwd=root,env=env,capture_output=True,text=True)
print(r.stdout[-3500:]); print(r.stderr[-800:]); s.stop(); print('exit',r.returncode)
