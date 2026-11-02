from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
G=Path('/Users/alexy/src/sail-sdp-gate');R=Path('/Users/alexy/src/sail-pipelines-proposal');gold='crates/sail-sql-parser/tests/gold_data/syntax.json';candidate='29d41f794acd1fe2138c37f1856efb9c9ea936c1';base='4fca6f3d4982e2639061094ededdd12a50f8ad1c'
def git(*a):return subprocess.check_output(['git','-C',str(G),*a])
assert git('rev-parse','HEAD').decode().strip()==candidate and not git('status','--porcelain').strip()
cmd=['cargo','+1.98.1','test','-p','sail-sql-parser','--test','syntax','--locked'];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':str(R/'.venv/bin/python'),'VIRTUAL_ENV':str(R/'.venv'),'PYTHONPATH':str(R/'.venv/lib/python3.12/site-packages')};receipt={'checks':[]}
original=git('show',base+':'+gold);Path('/tmp/sail-sdp-syntax-golden-before.json').write_bytes(original)
for rev,label,update in [(candidate,'candidate-generate',True),(base,'baseline-check',False),(base,'baseline-generate',True)]:
 if git('rev-parse','HEAD').decode().strip()!=rev:subprocess.run(['git','-C',str(G),'checkout','--detach',rev],check=True)
 log=Path('/tmp/sail-sdp-syntax-'+label+'.log')
 with log.open('x')as out:result=subprocess.run(cmd,cwd=G,env={**env,**({'SAIL_UPDATE_GOLD_DATA':'1'}if update else{})},stdout=out,stderr=subprocess.STDOUT)
 receipt['checks'].append({'commit':rev,'command':cmd,'update':update,'exit_code':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 assert result.returncode==(0 if update else 101)
 if update:
  Path('/tmp/sail-sdp-syntax-'+label+'.json').write_bytes((G/gold).read_bytes());(G/gold).write_bytes(original)
 assert not git('status','--porcelain').strip()
print('Generated candidate and baseline snapshots; comparing',flush=True)
a=Path('/tmp/sail-sdp-syntax-candidate-generate.json').read_bytes();b=Path('/tmp/sail-sdp-syntax-baseline-generate.json').read_bytes();assert a==b
receipt.update(recorded_at=datetime.now(timezone.utc).isoformat(),before_sha256=hashlib.sha256(original).hexdigest(),generated_sha256=hashlib.sha256(a).hexdigest(),same_generated_snapshot=True)
Path('/tmp/sail-sdp-syntax-golden-probe.json').write_text(json.dumps(receipt,indent=2)+'\n')
(R/gold).write_bytes(a)
subprocess.run(['git','-C',str(G),'checkout','--detach',candidate],check=True)
print('PASS baseline also fails;both official generations byte-identical;baseline golden repair prepared separately')
