"""Close immutable pre-delivery component evidence after exact gate and review."""
import argparse,hashlib,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);a=p.parse_args()
out=Path(__file__).parent.resolve();repo=Path('/private/tmp/sail-argentea-rank-wcc-input-lifetime');gate=Path('/private/tmp/sail-rank-wcc-lifetime-gate')
head='33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9';tree='3f4399056199b49708340abf0b4d1205fca860dd';base='a3462345a6764096024c055dc4d105a3c634e5a4'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text())
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).decode().strip()
assert not (out/'final-receipt.json').exists() and not (out/'files-manifest.json').exists()
for root in (repo,gate):assert git(root,'rev-parse','HEAD')==head and git(root,'write-tree')==tree and not git(root,'status','--porcelain')
assert git(repo,'symbolic-ref','--short','HEAD')=='work/argentea-rank-wcc-input-lifetime'
assert subprocess.run(['git','-C',str(gate),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
assert git(repo,'rev-parse','HEAD^^')==base
pin=load(out/'extended-frozen.json')
for name,digest in pin['paths'].items():assert sha(repo/name)==digest==sha(gate/name)
exact=load(out/'extended-exact-gate/receipt.json');candidate=load(out/'extended-candidate-gate/receipt.json')
assert exact['outcome']=='PASS' and exact['exact'] and exact['head']==head and exact['tree']==tree
assert candidate['outcome']=='PASS' and not candidate['exact'] and candidate['tree']==tree
assert exact['all_saturators_reaped'] and candidate['all_saturators_reaped']
for folder,receipt in [('extended-exact-gate',exact),('extended-candidate-gate',candidate)]:
 for step in receipt['steps']:
  assert step['outcome']=='PASS' and sha(out/folder/step['log'])==step['log_sha256']
  if step['name'] in ('core-release','core-loaded'):assert step['tests_passed']==136
  if step['name'] in ('native-release','native-loaded'):assert step['tests_passed']==55 and step['argentea_tests_passed']==49
assert sha(out/'run_extended_gate.py')==exact['script_sha256']==pin['driver_sha256']
audit=load(a.audit)
assert audit['commit']==head and audit['tree']==tree and audit['outcome']=='PASS_INDEPENDENT_EXPANDED_SOURCE_AND_EXACT_GATE_AUDIT'
rebind=load(out/'independent-readme-rebind.json')
assert rebind['outcome']=='PASS_NARROW_README_CLARIFICATION_REBIND' and rebind['commit']==head and rebind['tree']==tree
assert rebind['independent_exact_audit_sha256']==sha(a.audit) and rebind['readme_sha256']==sha(out/'README.md')
prior=(out/'README.md').read_text().replace(rebind['only_change']['after'],rebind['only_change']['before'])
assert hashlib.sha256(prior.encode()).hexdigest()==rebind['prior_readme_sha256']
for name,digest in audit['inputs'].items():
 if name=='argentea-rank-wcc-input-lifetime/README.md':assert digest==rebind['prior_readme_sha256']
 else:assert sha(out.parent/name)==digest
comparison=load(out/'allocation-comparison.json');assert comparison['commit']==head and len(comparison['rows'])==72
for kind in ('baseline','candidate'):
 native=load(out/(kind+'-native-extended01')/'receipt.json')
 assert len(native['lifetime_rows'])==8 and native['source_unchanged']
 assert native['outcome']==('EXPECTED_BASELINE_FAILURE' if kind=='baseline' else 'PASS_ACTUAL_ADAPTER_CONTROLS')
cursor=out.parent/'argentea-cursor-lease-control/final-receipt.json'
assert cursor.exists()
receipt=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='EXACT_COMPONENT_GATE_PASS',repository='querygraph/sail',branch='work/argentea-rank-wcc-input-lifetime',commit=head,tree=tree,base_commit=base,commits=git(repo,'rev-list','--reverse',base+'..HEAD').splitlines(),source_clean=True,changed_paths=pin['paths'],candidate_gate='extended-candidate-gate/receipt.json',candidate_gate_receipt_sha256=sha(out/'extended-candidate-gate/receipt.json'),exact_gate='extended-exact-gate/receipt.json',exact_gate_receipt_sha256=sha(out/'extended-exact-gate/receipt.json'),independent_audit=str(a.audit.resolve().relative_to(out)),independent_audit_sha256=sha(a.audit),readme_rebind='independent-readme-rebind.json',readme_rebind_sha256=sha(out/'independent-readme-rebind.json'),cursor_evidence='../argentea-cursor-lease-control/final-receipt.json',cursor_evidence_sha256=sha(cursor),allocation_comparison_sha256=sha(out/'allocation-comparison.json'),readme_sha256=sha(out/'README.md'),tests=dict(core=136,native=55,argentea_native=49,ordinary_and_loaded=True,loaded_cores=len(exact['saturation'])),measurements=dict(core_allocation_cells=72,core_matched_pairs=36,actual_adapter_cells=8,larger_fixtures_admission_peak_unchanged=True),delivery='NOT_PUSHED_AT_EVIDENCE_CUTOFF',limits=['Requested allocation sizes/admission only; no RSS or timing claims','No host/CLI/SQL/Linux/worker/Flight or combined-wheel qualification','No historical zero-OOM stream-cause attribution','Raw input still overlaps CSR construction','Borrowed and prepared cost/protocol traces are candidate API comparisons; original production baselines are separately retained for lease and actual adapter controls'],manifest='files-manifest.json')
with (out/'final-receipt.json').open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
files=[]
for path in sorted(out.rglob('*')):
 if path.is_file():
  assert not path.is_symlink() and '__pycache__' not in path.parts
  if path.suffix=='.json':json.loads(path.read_text())
  files.append(dict(path=str(path.relative_to(out)),sha256=sha(path),bytes=path.stat().st_size))
manifest=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),commit=head,scope='All retained component evidence including failed/intermediate attempts; excludes only this manifest itself and the separately manifested cursor sibling.',files=files)
with (out/'files-manifest.json').open('x') as stream:json.dump(manifest,stream,indent=2);stream.write('\n')
print(json.dumps(dict(commit=head,outcome=receipt['outcome'],files=len(files),final_receipt_sha256=sha(out/'final-receipt.json'),manifest_sha256=sha(out/'files-manifest.json')),indent=2))
