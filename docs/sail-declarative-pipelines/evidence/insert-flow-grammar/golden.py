from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
G=Path('/Users/alexy/src/sail-sdp-gate');R=Path('/Users/alexy/src/sail-pipelines-proposal');c=json.loads(Path('/tmp/sail-sdp-insert-flow-grammar-03-candidate.json').read_text());base=c['commit']
def git(*a):return subprocess.check_output(['git','-C',str(G),*a])
assert git('rev-parse','HEAD').decode().strip()==base and not git('status','--porcelain').strip()
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':str(R/'.venv/bin/python'),'PYTHONPATH':str(R/'.venv/lib/python3.12/site-packages'),'VIRTUAL_ENV':str(R/'.venv')};receipt={'sail_commit':base,'checks':[]}
for label,package,selector,update in [('native-analyzer','sail-sql-analyzer',None,False),('plan-generate','sail-spark-connect','proto::plan::tests::test_sql_to_plan',True),('function-generate','sail-spark-connect','proto::function::tests::test_sql_function',True)]:
 cmd=['cargo','+1.98.1','test','-p',package,'--lib','--locked',*([selector]if selector else[])];log=Path('/tmp/sail-sdp-insert-flow-'+label+'.log')
 with log.open('x')as out:r=subprocess.run(cmd,cwd=G,env={**env,**({'SAIL_UPDATE_GOLD_DATA':'1'}if update else{})},stdout=out,stderr=subprocess.STDOUT)
 receipt['checks'].append({'name':label,'command':cmd,'update':update,'exit_code':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 Path('/tmp/sail-sdp-insert-flow-golden.json').write_text(json.dumps({**receipt,'recorded_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
 assert r.returncode==0,log.read_text()[-4000:]
 print('PASS '+label,flush=True)
changed=git('diff','--name-only').decode().splitlines();deltas=[]
assert changed
for path in changed:
 assert path.startswith('crates/sail-spark-connect/tests/gold_data/') and path.endswith('.json')
 before=git('show',base+':'+path);after=(G/path).read_bytes();a=json.loads(before);b=json.loads(after)
 assert set(a)==set(b) and len(a['tests'])==len(b['tests'])
 changes=[]
 for i,(old,new)in enumerate(zip(a['tests'],b['tests'])):
  assert {k:v for k,v in old.items()if k!='output'}=={k:v for k,v in new.items()if k!='output'},(path,i)
  if old!=new:
   assert 'failure'in new['output'],(path,i,'unexpected successful-output change')
   assert 'failure'in old['output'] or old.get('exception'),(path,i,'new failure without prior failure or Spark exception')
   changes.append({'index':i,'input':old['input'],'exception':old.get('exception'),'before':old['output'],'after':new['output']})
 deltas.append({'path':path,'cases':len(a['tests']),'changed':changes,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()})
 (R/path).write_bytes(after)
 (G/path).write_bytes(before)
Path('/tmp/sail-sdp-insert-flow-golden-delta.json').write_text(json.dumps(deltas,indent=2)+'\n')
assert not git('status','--porcelain').strip() and git('rev-parse','HEAD').decode().strip()==base
print('PASS golden inputs/Spark exceptions/unrelated outputs unchanged;files',len(changed),'outputs',sum(len(d['changed'])for d in deltas))
