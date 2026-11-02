from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,os,subprocess
G=Path('/Users/alexy/src/grust-sdp-review-gate');R=Path('/tmp/sail-sdp-scala-reference-expanded-qualified-02');R.mkdir();PY='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-evidence-candidate.json').read_text());assert subprocess.check_output(['git','-C',str(G),'rev-parse','HEAD'],text=True).strip()==c['commit']
base=[PY,str(G/'scripts/sdp-scala-reference/run.py'),'--spark-source','/Users/alexy/src/spark-sdp-4.2.1','--spark-home','/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark','--java-home','/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home','--python',PY,'--cache','/tmp/sail-sdp-scala-suite-substrate/artifacts']
commands=[('ruff',['uv','tool','run','--offline','ruff==0.17.3','check','scripts/sdp-scala-reference']),('format',['uv','tool','run','--offline','ruff==0.17.3','format','--check','scripts/sdp-scala-reference']),('collect',base+['--output',str(R/'collect'),'collect'])]
for label,suite in [
 ('mv-parser','org.apache.spark.sql.execution.command.v2.CreateMaterializedViewAsSelectParserSuite'),
 ('st-as-parser','org.apache.spark.sql.execution.command.v2.CreateStreamingTableAsSelectParserSuite'),
 ('st-parser','org.apache.spark.sql.execution.command.v2.CreateStreamingTableParserSuite'),
 ('flow-parser','org.apache.spark.sql.execution.command.v2.CreateFlowCommandSuite'),
 ('ddl','org.apache.spark.sql.execution.command.InMemoryCatalogedDDLSuite'),
 ('hive-ddl','org.apache.spark.sql.hive.execution.HiveDDLSuite'),
 ('default','org.apache.spark.sql.pipelines.graph.DefaultMaterializeTablesSuite'),
 ('hive','org.apache.spark.sql.hive.pipelines.HiveMaterializeTablesSuite')]:
 commands.append((label,base+['--output',str(R/label),'run','--registration',str(R/'collect/suites.json'),'--suite',suite]))
r={'commit':c['commit'],'scope':'Exact tool gate and original Spark reference suites; no Sail acceptance','started_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
for name,cmd in commands:
 assert subprocess.check_output(['git','-C',str(G),'rev-parse','HEAD'],text=True).strip()==c['commit']
 log=R/(name+'.log')
 with log.open('w')as out:p=subprocess.run(cmd,cwd=G,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=out,stderr=subprocess.STDOUT)
 r['checks'].append({'name':name,'command':cmd,'exit_code':p.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()});(R/'gate.json').write_text(json.dumps(r,indent=2)+'\n')
 print(name,p.returncode,log.read_text()[-1500:],flush=True)
 if p.returncode:raise SystemExit(p.returncode)
rows=json.loads((R/'collect/suites.json').read_text());assert sum(bool(x['testNames'])for x in rows)==43 and sum(len(x['testNames'])for x in rows)==595 and not any(x['status']=='unresolved'or x['nestedSuiteIds']or x['tags']for x in rows)
for name in ['collect','mv-parser','st-as-parser','st-parser','flow-parser','ddl','hive-ddl','default','hive']:
 x=json.loads((R/name/'receipt.json').read_text());assert x['outcome']=='passed' and len(x['bindings'])==56
assert not subprocess.check_output(['git','-C',str(G),'status','--porcelain'],text=True).strip()
r.update(outcome='passed',completed_at=datetime.now(timezone.utc).isoformat());(R/'gate.json').write_text(json.dumps(r,indent=2)+'\n');print('PASS exact expanded Scala reference tool:43 nonempty suites595 scoped names; parser33+DDL6+metadata58 reference cases; no Sail claim',flush=True)
