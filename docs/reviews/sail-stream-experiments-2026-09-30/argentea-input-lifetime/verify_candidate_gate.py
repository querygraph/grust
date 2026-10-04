"""Validate the completed detached gate and frozen candidate before committing."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
out=Path(__file__).parent
source=json.loads((out/'candidate-source.json').read_text())
r=json.loads((out/'candidate-gate02/receipt.json').read_text())
assert r['verdict']=='PASS' and r['all_load_reaped']
assert r['head']==source['head'] and r['index_tree']==source['index_tree']
assert r['source_hashes']==source['source_hashes']
expected={'diff-check':None,'core-format':None,'native-changed-format':None,'core-clippy':None,'core-release':120,'native-release':51,'core-loaded':120,'native-loaded':51}
assert {s['name']:s.get('tests_passed') for s in r['steps']}==expected
for s in r['steps']:
 assert s['returncode']==0
 if s['name'] in ['native-release','native-loaded']:assert s['argentea_tests_passed']==45
 if s['name'].endswith('-loaded'):assert s['load_alive_before']==s['load_alive_after']==r['load_process_count']
for path,detached in [('/private/tmp/sail-argentea-owned-input',False),('/private/tmp/sail-argentea-owned-input-gate',True)]:
 def git(*a):return subprocess.check_output(['git','-C',path,*a],text=True).strip()
 assert git('rev-parse','HEAD')==source['head']
 assert git('write-tree')==source['index_tree']
 assert not git('diff','--name-only') and not git('ls-files','--others','--exclude-standard')
 assert set(git('diff','--cached','--name-only').splitlines())==set(source['source_hashes'])
 branch=subprocess.run(['git','-C',path,'symbolic-ref','-q','HEAD'],capture_output=True,text=True)
 assert branch.returncode==1 if detached else branch.stdout.strip()=='refs/heads/work/argentea-owned-input'
 assert all(hashlib.sha256((Path(path)/n).read_bytes()).hexdigest()==h for n,h in source['source_hashes'].items())
assert hashlib.sha256((out/'run_gate.py').read_bytes()).hexdigest()==r['script_sha256']
record={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'PASS_FROZEN_DETACHED_GATE_RECEIPT','head':source['head'],'index_tree':source['index_tree'],'gate_receipt_sha256':hashlib.sha256((out/'candidate-gate02/receipt.json').read_bytes()).hexdigest(),'source_hashes':source['source_hashes'],'scope':'Validates completed detached tests and exact unchanged source, before git commit in the same && chain; no new test run claim.'}
with (out/'precommit-gate-verification.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(record['outcome'],source['index_tree'])
