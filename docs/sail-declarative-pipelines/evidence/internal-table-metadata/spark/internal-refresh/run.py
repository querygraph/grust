from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/tmp/sail-sdp-internal-refresh')
home=Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark')
java=Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home')
env={**os.environ,'JAVA_HOME':str(java),'SPARK_LOCAL_IP':'127.0.0.1'}
commands=[
[str(java/'bin/java'),'-cp',str(home/'jars/*'),'scala.tools.nsc.Main','-usejavacp','-d',str(root/'classes'),str(root/'TestGraphRegistrationContext.scala'),str(root/'RefreshOracle.scala')],
[str(java/'bin/jar'),'cf',str(root/'oracle.jar'),'-C',str(root/'classes'),'.'],
[str(home/'bin/spark-submit'),'--class','org.apache.spark.sql.pipelines.graph.RefreshOracle',str(root/'oracle.jar'),str(root/'data')]]
checks=[]
for i,cmd in enumerate(commands):
 p=root/f'check-{i}.log'
 with p.open('w')as f:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
 checks.append({'command':cmd,'exit_code':r.returncode,'log':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 (root/'receipt.json').write_text(json.dumps({'spark_source_commit':'617618396087429b5627a86ce933bb0f5d6645cb','checks':checks},indent=2)+'\n')
 print(p.read_text()[-4000:],flush=True)
 if r.returncode:raise SystemExit(r.returncode)
