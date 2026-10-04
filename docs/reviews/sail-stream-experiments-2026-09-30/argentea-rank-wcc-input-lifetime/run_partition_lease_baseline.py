"""Unchanged a346 production plus one sole-owner drop test module."""
import hashlib,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
repo=Path('/private/tmp/sail-rank-wcc-lifetime-baseline')
out=Path(__file__).parent
base='a3462345a6764096024c055dc4d105a3c634e5a4'
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0',CARGO_INCREMENTAL='0',CARGO_NET_OFFLINE='true',CARGO_TARGET_DIR='/private/tmp/sail-rank-wcc-lifetime-target/core')
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],env=env).decode().strip()
def snapshot():
    assert git('rev-parse','HEAD')==base
    assert subprocess.run(['git','-C',str(repo),'symbolic-ref','-q','HEAD'],env=env,capture_output=True).returncode==1
    assert not git('diff','--name-only')
    assert not git('ls-files','--others','--exclude-standard')
    return dict(head=base,tree=git('write-tree'),files={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in git('ls-files').splitlines()})
start=datetime.now(timezone.utc).isoformat()
before=snapshot()
command=['cargo','test','--manifest-path','examples/extensions/argentea/Cargo.toml','--release','--locked','--offline','--test','partition_lease','--','--nocapture']
with (out/'partition-lease-baseline.log').open('x') as log:
    result=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT)
after=snapshot()
assert after==before
text=(out/'partition-lease-baseline.log').read_text()
assert result.returncode==101,text
assert '0 passed; 3 failed; 0 ignored; 0 measured; 0 filtered out' in text,text
receipt=dict(started_utc=start,finished_utc=datetime.now(timezone.utc).isoformat(),outcome='BASELINE_REPRODUCED',command=command,returncode=result.returncode,source=before,source_unchanged=True,log_sha256=hashlib.sha256(text.encode()).hexdigest(),scope='Unchanged production; BFS/SSSP/residual PageRank successful sole-owner drop callbacks failed before fix. Requested admission live bytes at lease callback are not RSS or a runtime stream-cause claim.')
(out/'partition-lease-baseline-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='source'},indent=2))
