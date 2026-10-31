from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
R=Path(__file__).resolve().parent;out=R/'enumerate-attempt-02';out.mkdir();home=Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark');java=Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home')
cmds=[[str(java/'bin/java'),'-cp',str(home/'jars/*')+os.pathsep+str(R/'artifacts/*'),'scala.tools.nsc.Main','-usejavacp','-d',str(R/'enumerator-classes'),str(R/'EnumerateSuites.scala')],[str(java/'bin/jar'),'cf',str(R/'enumerator.jar'),'-C',str(R/'enumerator-classes'),'.'],[str(home/'bin/spark-submit'),'--master','local[2]','--driver-class-path',str(R/'artifacts/*'),'--driver-java-options',f'-ea -Dspark.testing=1 -Dspark.test.home=/Users/alexy/src/spark-sdp-4.2.1','--class','org.apache.spark.sql.pipelines.conformance.EnumerateSuites',str(R/'enumerator.jar'),str(out/'suites.json'),str(R/'artifacts/spark-pipelines_2.13-4.2.1-tests.jar'),str(R/'artifacts/spark-connect_2.13-4.2.1-tests.jar')]]
checks=[]
for i,cmd in enumerate(cmds):
 log=out/f'{i}.log'
 with log.open('w')as f:r=subprocess.run(cmd,cwd=out,env={**os.environ,'JAVA_HOME':str(java),'SPARK_LOCAL_IP':'127.0.0.1'},stdout=f,stderr=subprocess.STDOUT)
 checks.append({'command':cmd,'exit_code':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 (out/'receipt.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'scope':'ScalaTest suite registration on Spark reference; no Sail execution'},indent=2)+'\n')
 print(log.read_text()[-3000:],flush=True)
 if r.returncode:raise SystemExit(r.returncode)
