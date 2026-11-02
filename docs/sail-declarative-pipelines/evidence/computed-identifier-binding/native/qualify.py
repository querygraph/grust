from pathlib import Path
import hashlib,json,re,subprocess
base=json.loads(Path('/tmp/sail-sdp-late-bound-scope-v2-candidate.json').read_text())['commit']
r=json.loads(Path('/tmp/sail-sdp-late-bound-scope-v2-gate.json').read_text());assert r['sail_commit']==base and r['outcome']=='passed'
for c in r['checks']:assert c['exit_code']==0 and hashlib.sha256(Path(c['log']).read_bytes()).hexdigest()==c['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-late-bound-scope-v2-rust.log').read_text())==['94','176']
for label in ['lookup','namespace']:
 c=json.loads(Path('/tmp/sail-sdp-late-bound-'+label+'-control.json').read_text());log=Path('/tmp/sail-sdp-late-bound-'+label+'-control.log').read_bytes()
 assert c['base']==base and c['exit_code']==101 and hashlib.sha256(log).hexdigest()==c['log_sha256'] and b'1 passed; 1 failed;' in log
 test='crates/sail-plan/src/resolver/query/late_bound_scope_tests.rs'
 for commit in [base,c['control']]:assert subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','rev-parse',commit+':'+test],text=True).strip()==c['test_blob']
assert subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','rev-parse','HEAD'],text=True).strip()==base
assert not subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','status','--porcelain'],text=True).strip()
print('PASS exact native94+176 and independent unchanged lookup/namespace controls')
