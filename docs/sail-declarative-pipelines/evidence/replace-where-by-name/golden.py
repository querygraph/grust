from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
G=Path('/Users/alexy/src/sail-sdp-gate');R=Path('/Users/alexy/src/sail-pipelines-proposal');c=json.loads(Path('/tmp/sail-sdp-replace-where-by-name-01-candidate.json').read_text());base=c['commit']
def git(*a):return subprocess.check_output(['git','-C',str(G),*a])
assert git('rev-parse','HEAD').decode().strip()==base and not git('status','--porcelain').strip()
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':str(R/'.venv/bin/python'),'VIRTUAL_ENV':str(R/'.venv'),'PYTHONPATH':str(R/'.venv/lib/python3.12/site-packages')};checks=[]
for label,cmd,update in [
 ('analyzer',['cargo','+1.98.1','test','-p','sail-sql-analyzer','--lib','--locked'],False),
 ('plan',['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','proto::plan::tests::test_sql_to_plan'],True),
 ('syntax',['cargo','+1.98.1','test','-p','sail-sql-parser','--test','syntax','--locked'],True)]:
 log=Path('/tmp/sail-sdp-replace-where-'+label+'.log')
 with log.open('x')as out:r=subprocess.run(cmd,cwd=G,env={**env,**({'SAIL_UPDATE_GOLD_DATA':'1'}if update else{})},stdout=out,stderr=subprocess.STDOUT)
 checks.append({'name':label,'command':cmd,'exit_code':r.returncode,'update':update,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()});Path('/tmp/sail-sdp-replace-where-golden.json').write_text(json.dumps({'sail_commit':base,'checks':checks,'recorded_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
 assert r.returncode==0,log.read_text()[-4000:]
 print('PASS '+label,flush=True)
deltas=[]
for path in git('diff','--name-only').decode().splitlines():
 assert path in ['crates/sail-spark-connect/tests/gold_data/plan/ddl_insert_into.json','crates/sail-sql-parser/tests/gold_data/syntax.json']
 a=json.loads(git('show',base+':'+path));b=json.loads((G/path).read_text());assert len(a['tests'])==len(b['tests']);changed=[]
 for i,(x,y)in enumerate(zip(a['tests'],b['tests'])):
  assert {k:v for k,v in x.items()if k!='output'}=={k:v for k,v in y.items()if k!='output'}
  if x!=y:changed.append({'index':i,'input':x['input'],'exception':x.get('exception'),'before':x['output'],'after':y['output']})
 deltas.append({'path':path,'cases':len(a['tests']),'changed':changed});(R/path).write_bytes((G/path).read_bytes());(G/path).write_bytes(git('show',base+':'+path))
Path('/tmp/sail-sdp-replace-where-golden-delta.json').write_text(json.dumps(deltas,indent=2)+'\n');assert not git('status','--porcelain').strip();print('PASS official generated snapshot/plan deltas,unchanged inputs/Spark exceptions',flush=True)
