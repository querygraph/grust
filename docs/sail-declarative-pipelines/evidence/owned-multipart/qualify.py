from pathlib import Path
import json,hashlib,subprocess
root=Path('/Users/alexy/src/sail-sdp-gate')
label='owned-multipart-qualified-final'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
s=json.loads(Path('/tmp/sail-sdp-'+label+'-sail-object-store-release/receipt.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
assert g['outcome']=='passed' and g['sail_commit']==s['commit']==c['commit']
for check in g['checks']:
 assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert '33 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
assert s['outcome']=='passed' and s['build_exit']==s['test_exit']==0
assert len(s['load_pids'])==s['logical_cpus']==len(s['load_worker_exit_codes'])
assert all(code is not None for code in s['load_worker_exit_codes'])
for pid in s['load_pids']:
 r=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
 assert r.returncode!=0 or '/usr/bin/yes' not in r.stdout,(pid,r.stdout)
assert hashlib.sha256(Path(s['binary']).read_bytes()).hexdigest()==s['binary_sha256']
assert '16 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-sail-object-store-release/test.log').read_text()
control=json.loads(Path('/tmp/sail-sdp-owned-multipart-notification-control-candidate.json').read_text())
assert git('rev-parse',control['commit']+':crates/sail-object-store/src/owned_multipart/tests_notification.rs')==git('rev-parse',c['commit']+':crates/sail-object-store/src/owned_multipart/tests_notification.rs')
assert 'part notification held admission lock' in Path('/tmp/sail-sdp-owned-multipart-notification-detached-control.log').read_text()
assert git('rev-parse',c['base']+':Cargo.lock')==git('rev-parse',c['commit']+':Cargo.lock')
assert git('rev-parse',c['base']+':crates/sail-object-store/Cargo.toml')==git('rev-parse',c['commit']+':crates/sail-object-store/Cargo.toml')
print('PASS exact multipart library/release/control/binary/dependency qualification '+c['commit'])
