"""Run one detached native control with a private target and exact source receipt."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument('kind',choices=['baseline','candidate']);a=p.parse_args()
repo=Path('/private/tmp/sail-owned-input-baseline' if a.kind=='baseline' else '/private/tmp/sail-argentea-owned-input-gate')
out=Path(__file__).parent/(a.kind+'-native-control');out.mkdir(exist_ok=False)
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
head=git('rev-parse','HEAD');tree=git('write-tree')
assert head=='200d1cf8eb1db5e9057e09e071ebd57391f4b376'
assert subprocess.run(['git','-C',str(repo),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
assert not git('diff','--name-only')
assert not git('ls-files','--others','--exclude-standard')
free=shutil.disk_usage(repo).free;assert free>32*1024**3
py='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'
config=json.loads(subprocess.check_output([py,'-c','import json,sys,sysconfig;print(json.dumps(dict(base=sys.base_prefix,lib=sysconfig.get_config_var("LIBDIR"))))'],text=True))
env=dict(CARGO_INCREMENTAL='0',CARGO_BUILD_JOBS='4',CARGO_TARGET_DIR='/private/tmp/sail-owned-input-'+('baseline-native' if a.kind=='baseline' else 'native')+'-target',PYO3_PYTHON=py,PYTHONHOME=config['base'],PYTHONPATH='/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/lib/python3.12/site-packages',DYLD_LIBRARY_PATH=config['lib'])
cmd=['cargo','test','--manifest-path',str(repo/'examples/extensions/nutmeg/Cargo.toml'),'--locked','--release','--lib','initialization_releases_raw_input_before_state','--','--nocapture']
r=dict(started_utc=datetime.now(timezone.utc).isoformat(),repository='querygraph/sail',source_scope='base HEAD plus staged control/candidate patch; not an exact commit verdict',head=head,index_tree=tree,environment=env,command=cmd,free_disk_bytes=free,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:result=subprocess.run(cmd,cwd=repo,env=dict(os.environ,**env),stdout=stdout,stderr=stderr)
r.update(returncode=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),observed_head=git('rev-parse','HEAD'),observed_index_tree=git('write-tree'))
assert r['observed_head']==head and r['observed_index_tree']==tree
r['expected_result']='both controls fail because old adapter retains raw admission' if a.kind=='baseline' else 'both controls pass'
(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r))
raise SystemExit(result.returncode)
