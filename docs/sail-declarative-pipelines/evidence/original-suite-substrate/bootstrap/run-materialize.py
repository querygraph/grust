from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
R=Path(__file__).resolve().parent;out=R/'materialize-attempt-01';out.mkdir();(out/'xml').mkdir();(out/'tmp').mkdir()
home=Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark');java='/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home'
cmd=[str(home/'bin/spark-submit'),'--master','local[2]','--driver-class-path',str(R/'artifacts/*'),'--driver-java-options',f'-ea -Dspark.testing=1 -Dspark.test.home=/Users/alexy/src/spark-sdp-4.2.1 -Djava.io.tmpdir={out}/tmp','--class','org.scalatest.tools.Runner',str(R/'artifacts/scalatest-app_2.13-3.2.19.jar'),'-s','org.apache.spark.sql.pipelines.graph.DefaultMaterializeTablesSuite','-o','-u',str(out/'xml')]
with (out/'run.log').open('w')as log:r=subprocess.run(cmd,cwd=out,env={**os.environ,'JAVA_HOME':java,'SPARK_LOCAL_IP':'127.0.0.1'},stdout=log,stderr=subprocess.STDOUT)
(out/'receipt.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'command':cmd,'exit_code':r.returncode,'log_sha256':hashlib.sha256((out/'run.log').read_bytes()).hexdigest(),'scope':'Original unmodified published Spark ScalaTest suite against Spark reference, not Sail'},indent=2)+'\n')
print((out/'run.log').read_text()[-9000:]);raise SystemExit(r.returncode)
