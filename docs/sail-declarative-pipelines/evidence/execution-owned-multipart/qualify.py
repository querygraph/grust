from pathlib import Path
import subprocess,json,hashlib
root=Path('/Users/alexy/src/sail-sdp-gate');label='execution-owned-multipart-qualified'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-sail-execution-release/receipt.json').read_text());control=json.loads(Path('/tmp/sail-sdp-execution-multipart-unknown-control.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
assert g['sail_commit']==r['commit']==control['candidate']==c['commit'] and g['outcome']==r['outcome']=='passed'
for check in g['checks']:
 assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert '197 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
assert r['build_exit']==r['test_exit']==0 and len(r['load_pids'])==len(r['load_worker_exit_codes'])==r['logical_cpus']
assert all(code is not None for code in r['load_worker_exit_codes'])
for pid in r['load_pids']:
 process=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
 assert process.returncode!=0 or '/usr/bin/yes' not in process.stdout
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '5 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-sail-execution-release/test.log').read_text()
log=Path('/tmp/sail-sdp-execution-multipart-unknown-control.log')
assert control['actual_exit']==control['expected_exit']==101 and hashlib.sha256(log.read_bytes()).hexdigest()==control['log_sha256']
assert 'assertion failed: !cause.is_retryable()' in log.read_text()
tests='crates/sail-execution/src/owned_multipart_tests.rs'
assert git('rev-parse',c['commit']+':'+tests)==git('rev-parse',control['control']+':'+tests)
assert git('diff','--name-only',c['commit'],control['control'])=='crates/sail-execution/src/owned_multipart.rs'
for path in ['Cargo.lock','crates/sail-execution/Cargo.toml']:
 assert git('rev-parse',c['base']+':'+path)==git('rev-parse',c['commit']+':'+path)
print('PASS exact execution multipart library/release/control/dependency qualification '+c['commit'])
