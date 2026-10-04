"""Detached WCC inbox core/native gate with private nonincremental targets."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, time
p=argparse.ArgumentParser(); p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--tree',required=True);p.add_argument('--branch-head',required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
root=Path(__file__).parent
source=json.loads((root/'candidate-source.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(a.repo),*args],text=True).strip()
def guard():
 assert git('rev-parse','HEAD')==a.head
 assert subprocess.run(['git','-C',str(a.repo),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
 assert git('rev-parse','refs/heads/work/argentea-wcc-inbox')==a.branch_head
 assert git('write-tree')==a.tree
 assert subprocess.run(['git','-C',str(a.repo),'diff','--quiet']).returncode==0
 assert not git('ls-files','--others','--exclude-standard')
 assert all(hashlib.sha256((a.repo/name).read_bytes()).hexdigest()==digest for name,digest in source['source_hashes'].items())
base_env=dict(CARGO_INCREMENTAL='0',CARGO_BUILD_JOBS='4')
core_env=dict(base_env,CARGO_TARGET_DIR='/private/tmp/sail-wcc-inbox-core-target')
native_env=dict(base_env,CARGO_TARGET_DIR='/private/tmp/sail-wcc-inbox-native-target',PYO3_PYTHON='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python',PYTHONHOME='/Users/alexy/.local/share/uv/python/cpython-3.12.8-macos-aarch64-none',PYTHONPATH='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/lib/python3.12/site-packages',DYLD_LIBRARY_PATH='/Users/alexy/.local/share/uv/python/cpython-3.12.8-macos-aarch64-none/lib')
manifest=lambda name:str(a.repo/f'examples/extensions/{name}/Cargo.toml')
core=['cargo','test','--manifest-path',manifest('argentea'),'--locked','--release','--','--nocapture']
native=['cargo','test','--manifest-path',manifest('nutmeg'),'--locked','--release','--lib','--','--nocapture']
r=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository='querygraph/sail',head=a.head,index_tree=a.tree,named_branch_head=a.branch_head,source_scope='exact commit' if git('rev-parse','HEAD^{tree}')==a.tree else 'precommit candidate: base HEAD plus staged patch, not a commit verdict',host=os.uname().nodename,free_disk_bytes=shutil.disk_usage(a.repo).free,source_hashes=source['source_hashes'],core_environment=core_env,native_environment=native_env,steps=[],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),format_scope='Full Argentea core fmt. No native source changed; inherited full native fmt failures retained separately in bfs-completion/baseline-native-format.',scope='Local core and full native adapter release tests, including every Argentea adapter test, under ordinary and saturated CPU. No remote or transport/performance claim.')
def run(name,command,env,count=None):
 with (a.output/(name+'.stdout')).open('w') as stdout,(a.output/(name+'.stderr')).open('w') as stderr:
  result=subprocess.run(command,cwd=a.repo,env=dict(os.environ,**env),stdout=stdout,stderr=stderr)
 step=dict(name=name,command=command,returncode=result.returncode)
 if count is not None:
  text=(a.output/(name+'.stdout')).read_text();step['summaries']=re.findall(r'^test result:.*$',text,re.M);step['tests_passed']=sum(int(n) for n in re.findall(r'^test result: ok\. (\d+) passed;',text,re.M));step['expected_count']=count
  if 'native' in name:step['argentea_tests_passed']=len(re.findall(r'^test argentea::\S+ \.\.\. ok$',text,re.M))
 r['steps'].append(step)
 assert result.returncode==0,name+' failed'
 if count is not None:assert step['tests_passed']==count,name+' inventory differs'
 if 'native' in name:assert step.get('argentea_tests_passed')==43,name+' Argentea inventory differs'
code=1;load=[]
try:
 guard();assert r['free_disk_bytes']>32*1024**3
 run('diff-check',['git','diff','--check','--cached'],core_env)
 run('core-format',['cargo','fmt','--manifest-path',manifest('argentea'),'--','--check'],core_env)
 run('core-clippy',['cargo','clippy','--manifest-path',manifest('argentea'),'--locked','--all-targets','--','-D','warnings'],core_env)
 run('core-release',core,core_env,113)
 run('native-release',native,native_env,49)
 load=[subprocess.Popen(['yes'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) for _ in range(os.cpu_count())];time.sleep(1)
 r['load_process_count']=len(load)
 for name,command,env,count in [('core-loaded',core,core_env,113),('native-loaded',native,native_env,49)]:
  alive=sum(x.poll() is None for x in load);assert alive==len(load)
  run(name,command,env,count)
  r['steps'][-1].update(load_alive_before=alive,load_alive_after=sum(x.poll() is None for x in load))
  assert r['steps'][-1]['load_alive_after']==len(load)
 guard();r['verdict']='PASS';code=0
except BaseException as error:r['verdict']='FAIL';r['error']=repr(error)
finally:
 for x in load:
  if x.poll() is None:x.terminate()
 for x in load:x.wait()
 r['all_load_reaped']=all(x.poll() is not None for x in load);r['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['observed_head']=git('rev-parse','HEAD');r['observed_tree']=git('write-tree');(a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
print('WCC_INBOX_GATE',r['verdict'],a.head,r['source_scope'],[(s['name'],s.get('tests_passed')) for s in r['steps']]);raise SystemExit(code)
