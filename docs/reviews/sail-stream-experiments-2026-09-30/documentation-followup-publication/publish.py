from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
R=Path('/private/tmp/grust-sail-review-followup-docs');O=Path('/private/tmp/grust-sail-review-followup-publication')
BASE='51644023a02185679527304682ed41055ae1c4aa';HEAD='f4443ba76c18c922698a060183c02ca65ce939c7'
REFS=['refs/heads/work/proposal-v5','refs/heads/work/sail-graph-review']
def git(*args):return subprocess.check_output(['git','-C',str(R),*args],text=True).strip()
def remote():return {line.split()[1]:line.split()[0] for line in git('ls-remote','origin',*REFS).splitlines()}
assert git('rev-parse','HEAD')==HEAD
assert git('rev-parse','HEAD^')==BASE,'publication must be exactly one fast-forward commit'
assert not git('status','--porcelain')
subprocess.run(['python3',str(O/'guard.py'),'exact-before',HEAD],check=True)
gate=json.loads((O/'exact-after-receipt.json').read_text());assert gate['head']==HEAD and gate['verdict']=='PASS'
before=remote();assert before==dict.fromkeys(REFS,BASE),before
# Explicit leases protect against any intervening remote change. Direct-parent
# and exact-old-ref guards above guarantee the intended updates are fast-forwards.
command=['git','-C',str(R),'push','--atomic',*[f'--force-with-lease={ref}:{BASE}' for ref in REFS],'origin',*[f'{HEAD}:{ref}' for ref in REFS]]
p=subprocess.run(command,text=True,capture_output=True)
(O/'push.stdout').write_text(p.stdout);(O/'push.stderr').write_text(p.stderr)
assert p.returncode==0,(p.returncode,p.stderr)
after=remote();assert after==dict.fromkeys(REFS,HEAD),after
receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'repository':'querygraph/grust','base_commit':BASE,'commit':HEAD,'tree':git('rev-parse','HEAD^{tree}'),'verdict':'DELIVERED_EXACT_DOCUMENTATION_GATE_PASS','remote_before':before,'remote_after':after,'push_command':command,'guards':'Clean detached exact tested SHA; exact parent/base proves fast-forward; both old refs checked and pinned by explicit leases in one atomic push; exact remote refs checked after. Shared local branches/index/files are not updated.','gate':gate,'independent_audit_sha256':hashlib.sha256((O/'independent-audit.json').read_bytes()).hexdigest(),'scope':'Documentation/evidence only; no runtime, release or performance qualification.'}
(O/'delivery.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'commit':HEAD,'remote_after':after,'verdict':receipt['verdict']},indent=2))
