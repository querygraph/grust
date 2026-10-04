"""Gate the exact combined review snapshot; host Rust is fingerprinted unchanged."""
from pathlib import Path
import argparse, datetime, hashlib, json, shutil, subprocess
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--tree',required=True);p.add_argument('--branch-head',required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
root=Path(__file__).parent;python='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'
def git(*args):return subprocess.check_output(['git','-C',str(a.repo),*args],text=True).strip()
def guard():
 assert git('rev-parse','HEAD')==a.head
 assert git('rev-parse','refs/heads/work/stream-review-followup')==a.branch_head
 assert git('write-tree')==a.tree
 assert subprocess.run(['git','-C',str(a.repo),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
 assert subprocess.run(['git','-C',str(a.repo),'diff','--quiet']).returncode==0
 assert not git('ls-files','--others','--exclude-standard')
def inventory(ref,paths):
 command=['ls-tree','-r',ref,'--',*paths] if ref else ['ls-files','-s','--',*paths]
 result={}
 for line in git(*command).splitlines():
  metadata,path=line.split('\t',1);values=metadata.split();result[path]=(values[0],values[2] if ref else values[1])
 return result
r=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository='querygraph/sail',head=a.head,index_tree=a.tree,branch_head=a.branch_head,scope='Experimental combined review snapshot; no default promotion, release, remote run or performance claim.',source_scope='exact commit' if git('rev-parse','HEAD^{tree}')==a.tree else 'precommit candidate: staged union, not a commit verdict',free_disk_bytes=shutil.disk_usage(a.repo).free,source_proofs=[],gates=[],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
code=1
try:
 guard();assert r['free_disk_bytes']>32*1024**3
 for label,ref,paths in [
  ('host Rust and workspace metadata','b569e75de625885b3d919fa4196b2e0bed14c618',['crates','Cargo.toml','Cargo.lock','rust-toolchain.toml']),
  ('Argentea core and native adapter','b4babe87cb50d16b4d439a0841a6291991c433d2',['examples/extensions/argentea','examples/extensions/nutmeg']),
  ('benchmark harness','c8fe857848f3ba1698ee0f9d1daf000790d691d4',['examples/extensions/benchmarks']),
  ('Pecan client','fe44428c9bfb43680affed0abae07240220df852',['examples/extensions/graph-algorithms'])]:
  expected,actual=inventory(ref,paths),inventory(None,paths);assert expected==actual,label+' source differs'
  name=label.split()[0].lower()+'-source-inventory.json';(a.output/name).write_text(json.dumps(actual,sort_keys=True,indent=2)+'\n')
  r['source_proofs'].append(dict(scope=label,reference=ref,tracked_files=len(actual),all_equal=True,inventory=name,inventory_sha256=hashlib.sha256((a.output/name).read_bytes()).hexdigest()))
 common=['--repo',str(a.repo),'--head',a.head,'--tree',a.tree,'--branch-head',a.branch_head]
 commands=[('native',['run_native_gate.py',*common,'--output',str(a.output/'native')]),
           ('benchmarks',['run_benchmark_gate.py',*common,'--output',str(a.output/'benchmarks')]),
           ('pecan',['run_pecan_gate.py','--repo',str(a.repo),'--output',str(a.output/'pecan'),'--source-receipt',str(root/'pecan-source-receipt.json')])]
 for label,args in commands:
  command=[python,str(root/args[0]),*args[1:]]
  with (a.output/(label+'.log')).open('w') as log:result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
  child=json.loads((a.output/label/'receipt.json').read_text()) if (a.output/label/'receipt.json').exists() else {}
  r['gates'].append(dict(name=label,command=command,returncode=result.returncode,receipt=str(Path(label)/'receipt.json'),verdict=child.get('verdict',child.get('outcome'))))
  assert result.returncode==0 and r['gates'][-1]['verdict'] in ('PASS','passed'),label+' gate failed'
 guard();r['verdict']='PASS';code=0
except BaseException as error:r['verdict']='FAIL';r['error']=repr(error)
finally:
 r['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['observed_head']=git('rev-parse','HEAD');r['observed_tree']=git('write-tree');(a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
print('FOLLOWUP_UNION_GATE',r['verdict'],a.head,r['source_scope']);raise SystemExit(code)
