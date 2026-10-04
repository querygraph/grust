"""Move the isolated detached gate to the newly committed matching tree and gate it."""
from pathlib import Path
import json,subprocess,sys
out=Path(__file__).parent
branch=Path('/private/tmp/sail-argentea-owned-input');gate=Path('/private/tmp/sail-argentea-owned-input-gate')
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
s=json.loads((out/'candidate-source.json').read_text())
head=git(branch,'rev-parse','HEAD')
assert git(branch,'rev-parse','HEAD^')==s['head']
assert git(branch,'rev-parse','HEAD^{tree}')==s['index_tree']
assert not git(branch,'status','--porcelain')
assert git(gate,'rev-parse','HEAD')==s['head'] and git(gate,'write-tree')==s['index_tree']
assert not git(gate,'diff','--name-only')
subprocess.run(['git','-C',str(gate),'checkout','--detach',head],check=True)
assert not git(gate,'status','--porcelain')
command=[sys.executable,str(out/'run_gate.py'),'--repo',str(gate),'--output',str(out/'exact-gate'),'--head',head,'--tree',s['index_tree'],'--branch-head',head]
raise SystemExit(subprocess.run(command).returncode)
