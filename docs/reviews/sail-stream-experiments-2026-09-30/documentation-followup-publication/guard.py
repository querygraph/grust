from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,subprocess,sys
ROOT=Path('/private/tmp/grust-sail-review-followup-docs')
OUT=Path('/private/tmp/grust-sail-review-followup-publication')
PIN=json.loads((OUT/'frozen.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()
audit_path=OUT/'independent-audit.json'
assert hashlib.sha256(audit_path.read_bytes()).hexdigest()=='715e64bf85df62783e38fe465efa6f41c8de5405b05eae07ed7e1038e916f98a'
audit=json.loads(audit_path.read_text())
assert audit['outcome']=='PASS_INDEPENDENT_PUBLICATION_AUDIT'
assert audit['frozen_index_tree']==PIN['tree']
assert audit['manifest_sha256']==PIN['manifest_sha256']
phase=sys.argv[1]
expected=PIN['base'] if phase.startswith('candidate') else sys.argv[2]
assert git('rev-parse','HEAD')==expected
assert subprocess.run(['git','-C',str(ROOT),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
assert git('write-tree')==PIN['tree']
assert subprocess.run(['git','-C',str(ROOT),'diff','--quiet']).returncode==0
assert not git('ls-files','--others','--exclude-standard')
assert hashlib.sha256((ROOT/PIN['manifest_path']).read_bytes()).hexdigest()==PIN['manifest_sha256']
if phase.startswith('exact'):
 assert git('rev-parse','HEAD^{tree}')==PIN['tree']
 assert not git('status','--porcelain')
if phase.endswith('after'):
 log=OUT/('candidate-gate.log' if phase.startswith('candidate') else 'exact-gate.log')
 data=log.read_text();assert data.endswith('SAIL_REVIEW_DOCUMENTATION PASSED '+expected+'\n')
 stats=json.loads(data[:data.rindex('\nSAIL_REVIEW_DOCUMENTATION')])
 receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'phase':phase,'head':expected,'tree':PIN['tree'],'gate':stats,'gate_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'verdict':'PASS','scope':'Documentation snapshot integrity only; no runtime gate.'}
 (OUT/(phase+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
print('DOCUMENTATION_SOURCE_GUARD PASSED '+phase+' '+expected+' '+PIN['tree'])
