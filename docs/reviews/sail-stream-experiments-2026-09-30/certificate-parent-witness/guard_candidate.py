"""No commit unless the final detached gate and matching named source pass."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
REPO=Path('/private/tmp/sail-certificate-parent-witness')
GATE=Path('/private/tmp/sail-certificate-parent-witness-gate')
ENV=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],env=ENV).decode().strip()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
pin=json.loads((OUT/'frozen.json').read_text())
for repo in (REPO,GATE):
    assert git(repo,'rev-parse','HEAD')==pin['base']
    assert git(repo,'write-tree')==pin['tree']
    assert not git(repo,'diff','--name-only')
    assert not git(repo,'ls-files','--others','--exclude-standard')
    assert set(git(repo,'diff','--cached','--name-only').splitlines())==set(pin['source_hashes'])
    assert pin['source_hashes']=={name:sha(repo/name) for name in pin['source_hashes']}
    subprocess.run(['git','-C',str(repo),'diff','--cached','--check'],env=ENV,check=True)
assert git(REPO,'branch','--show-current')==pin['branch']
assert not git(GATE,'branch','--show-current')
assert pin['helper_hashes']=={name:sha(OUT/name) for name in pin['helper_hashes']}
review=json.loads((OUT/'independent-source-review.json').read_text())
assert review['outcome']=='PASS_INDEPENDENT_PARENT_WITNESS_SOURCE_REVIEW'
assert review['tree']==pin['tree'] and review['source_hashes']==pin['source_hashes']
receipt=json.loads((OUT/'candidate-gate/receipt.json').read_text())
assert receipt['outcome']=='PASS' and receipt['head']==pin['base'] and receipt['tree']==pin['tree']
assert receipt['source_runtime_unchanged'] and receipt['server_reaped']
assert receipt['sql_counts']==dict(tests=71,failures=0,errors=0,skipped=0)
assert receipt['unit_counts']==dict(tests=473,failures=0,errors=0,skipped=136)
for name,digest in receipt['logs'].items():assert sha(OUT/'candidate-gate'/name)==digest
print('PARENT_WITNESS_CONDITIONAL_COMMIT_GUARD PASS',pin['tree'])
