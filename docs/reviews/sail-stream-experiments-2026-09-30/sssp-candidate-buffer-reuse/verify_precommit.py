"""Commit only the still-identical named branch after its detached candidate gate."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
out=Path(__file__).parent
pin=json.loads((out/'frozen.json').read_text()); repo=Path(pin['repo']);gate=Path(pin['gate'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(p,*a):return subprocess.check_output(['git','-C',str(p),*a],env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).decode().strip()
receipt=json.loads((out/'candidate-gate/receipt.json').read_text())
assert receipt['outcome']=='PASS' and receipt['head']==pin['base'] and receipt['tree']==pin['tree'] and not receipt['exact']
assert receipt['script_sha256']==pin['driver_sha256']==sha(out/'run_gate.py')
assert receipt['all_saturators_reaped']
assert git(repo,'symbolic-ref','--short','HEAD')==pin['branch']
for root in [repo,gate]:
 assert git(root,'rev-parse','HEAD')==pin['base'] and git(root,'write-tree')==pin['tree']
 assert not git(root,'diff','--name-only') and not git(root,'ls-files','--others','--exclude-standard')
 for path,digest in pin['paths'].items():assert sha(root/path)==digest
assert not (Path(receipt['target_root'])/'.sssp-candidate-gate.lock').exists()
for step in receipt['steps']:
 assert step['outcome']=='PASS'
 assert sha(out/'candidate-gate'/step['log'])==step['log_sha256']
result=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_PRECOMMIT_GUARDS',base=pin['base'],tree=pin['tree'],branch=pin['branch'],candidate_gate_receipt_sha256=sha(out/'candidate-gate/receipt.json'),frozen_sha256=sha(out/'frozen.json'))
with (out/'precommit-verification.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print('SSSP_REUSE_PRECOMMIT_GUARD PASSED',pin['tree'])
