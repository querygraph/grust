"""Detached actual-adapter allocation control; no host/remote execution."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from datetime import datetime,timezone
p=argparse.ArgumentParser();p.add_argument('kind',choices=['baseline','candidate']);p.add_argument('--attempt',default='01');a=p.parse_args()
repo=Path('/private/tmp/sail-rank-wcc-lifetime-'+('baseline' if a.kind=='baseline' else 'gate'))
out=Path(__file__).parent/(a.kind+'-native-control'+a.attempt);out.mkdir(exist_ok=False)
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
def utc():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],env=env).decode().strip()
def state():
 assert git('rev-parse','HEAD')=='a3462345a6764096024c055dc4d105a3c634e5a4'
 assert subprocess.run(['git','-C',str(repo),'symbolic-ref','-q','HEAD'],env=env,capture_output=True).returncode==1
 assert not git('diff','--name-only') and not git('ls-files','--others','--exclude-standard')
 return dict(head=git('rev-parse','HEAD'),tree=git('write-tree'),files={name:sha(repo/name) for name in git('ls-files').splitlines()})
before=state();(out/'source-before.json').write_text(json.dumps(before,indent=2)+'\n')
py='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'
probe={k:v for k,v in env.items() if k not in ['PYTHONHOME','PYTHONPATH','DYLD_LIBRARY_PATH','LD_LIBRARY_PATH']}
config=json.loads(subprocess.check_output([py,'-c','import json,sys,sysconfig;print(json.dumps(dict(version=list(sys.version_info[:3]),base=sys.base_prefix,lib=sysconfig.get_config_var("LIBDIR"),purelib=sysconfig.get_path("purelib"))))'],env=probe))
assert config['version']==[3,12,8]
selected=dict(CARGO_INCREMENTAL='0',CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='6',CARGO_TARGET_DIR='/private/tmp/sail-rank-wcc-lifetime-target/native',PYO3_PYTHON=py,PYTHONHOME=config['base'],PYTHONPATH=config['purelib'],DYLD_LIBRARY_PATH=config['lib'],PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',GIT_OPTIONAL_LOCKS='0',PATH=str(Path(py).parent)+os.pathsep+env['PATH'])
assert shutil.disk_usage(repo).free>=32*1024**3
cmd=['cargo','test','--manifest-path',str(repo/'examples/extensions/nutmeg/Cargo.toml'),'--locked','--offline','--release','--lib','initialization_releases_raw_vertex_storage','--','--nocapture']
receipt=dict(started_utc=utc(),kind=a.kind,head=before['head'],tree=before['tree'],source_before_sha256=sha(out/'source-before.json'),environment=selected,command=cmd,script_sha256=sha(Path(__file__)))
try:
 with (out/'stdout').open('x') as stdout,(out/'stderr').open('x') as stderr:
  result=subprocess.run(cmd,cwd=repo,env=dict(env,**selected),stdout=stdout,stderr=stderr)
 receipt['returncode']=result.returncode
 assert state()==before
 receipt['source_unchanged']=True
 expected=101 if a.kind=='baseline' else 0
 receipt['expected_returncode']=expected
 text=(out/'stdout').read_text()
 assert result.returncode==expected,text+(out/'stderr').read_text()
 summary='0 passed; 3 failed;' if a.kind=='baseline' else '3 passed; 0 failed;'
 assert summary in text,text
 receipt['outcome']='EXPECTED_BASELINE_FAILURE' if a.kind=='baseline' else 'PASS_ACTUAL_ADAPTER_CONTROLS'
except BaseException as error:
 receipt.update(outcome='FAIL',error=repr(error));raise
finally:
 receipt.update(finished_utc=utc(),stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'))
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
