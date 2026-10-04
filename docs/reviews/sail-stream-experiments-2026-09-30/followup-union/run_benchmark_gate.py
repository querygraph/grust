#!/usr/bin/env python3
"""Gate an immutable detached Python harness snapshot, without Rust builds."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--tree',required=True);p.add_argument('--branch-head',required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
python=Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python');root=Path(__file__).parent

def git(*args):return subprocess.check_output(['git','-C',str(a.repo),*args],text=True).strip()
def guard():
 assert git('rev-parse','HEAD')==a.head,'detached HEAD moved'
 assert subprocess.run(['git','-C',str(a.repo),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1,'gate is not detached'
 assert git('rev-parse','refs/heads/work/stream-review-followup')==a.branch_head,'named branch moved'
 assert git('write-tree')==a.tree,'gate index changed'
 assert subprocess.run(['git','-C',str(a.repo),'diff','--quiet']).returncode==0,'unstaged gate changes'
 assert not git('ls-files','--others','--exclude-standard'),'untracked gate files'

env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',CARGO_INCREMENTAL='0',CARGO_TARGET_DIR=str(a.output/'unused-cargo-target'))
for key in ['GRAPH500_SOURCE','GRAPH500_MATRIX_GENERATOR','GAP_CONTROL_BINARY','PARALLEL_CONTROL_BINARY','SAIL_GRAPH_TEST_REMOTE']:env.pop(key,None)
receipt={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repo':str(a.repo),'head':a.head,'index_tree':a.tree,'named_branch_head':a.branch_head,'source_scope':'exact commit' if git('rev-parse','HEAD^{tree}')==a.tree else 'precommit candidate: base HEAD plus staged patch, not a commit verdict','free_disk_bytes':shutil.disk_usage(a.repo).free,'steps':[],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
code=1
try:
 guard();assert receipt['free_disk_bytes']>1024**3
 commands=[('diff-check',['git','-C',str(a.repo),'diff','--check','--cached']),('python-tests',[str(python),'-m','pytest','-q','-p','no:cacheprovider','examples/extensions/benchmarks','--ignore=examples/extensions/benchmarks/test_wcc_certificate.py','--basetemp='+str(a.output/'pytest-temp'),'--junitxml='+str(a.output/'junit.xml')]),('local-sql-integration',[str(python),str(root/'run_integration.py'),'--repo',str(a.repo),'--output',str(a.output/'integration')])]
 for name,command in commands:
  with (a.output/(name+'.log')).open('w') as log:
   result=subprocess.run(command,cwd=a.repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  receipt['steps'].append({'name':name,'command':command,'returncode':result.returncode})
  assert result.returncode==0,name+' failed'
 guard()
 for label,file in [('python',a.output/'junit.xml'),('local_sql',a.output/'integration/junit.xml')]:
  suites=ET.parse(file).getroot(); receipt[label+'_tests']={k:sum(int(s.attrib[k]) for s in suites.iter('testsuite')) for k in ['tests','failures','errors','skipped']}
 code=0;receipt['verdict']='PASS'
except BaseException as e:receipt['verdict']='FAIL';receipt['error']=repr(e)
finally:
 receipt['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();receipt['observed_head']=git('rev-parse','HEAD');receipt['observed_index_tree']=git('write-tree');(a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt));raise SystemExit(code)
