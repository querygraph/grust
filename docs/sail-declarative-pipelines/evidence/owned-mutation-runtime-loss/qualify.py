from pathlib import Path
import hashlib,json,subprocess
root=Path('/Users/alexy/src/sail-sdp-gate');label='owned-mutation-runtime-loss'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
for check in g['checks']:
 assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
for count in [111,198]:assert str(count)+' passed; 0 failed' in log
for package,count in [('sail-common-datafusion',111),('sail-execution',6)]:
 p=Path('/tmp/sail-sdp-'+label+'-'+package+'-release');r=json.loads((p/'receipt.json').read_text())
 assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
 assert len(r['load_pids'])==len(r['load_worker_exit_codes'])==r['logical_cpus']==10
 assert all(code is not None for code in r['load_worker_exit_codes'])
 for pid in r['load_pids']:
  process=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
  assert process.returncode!=0 or '/usr/bin/yes' not in process.stdout
 assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
 assert str(count)+' passed; 0 failed' in (p/'test.log').read_text()
control=json.loads(Path('/tmp/sail-sdp-mutation-runtime-loss-counterexample-candidate.json').read_text())
assert control['base']==c['base']
assert sorted(git('diff','--name-only',control['base'],control['commit']).splitlines())==sorted(control['paths'])
path='crates/sail-execution/src/owned_multipart_runtime_tests.rs'
assert git('rev-parse',control['commit']+':'+path)==git('rev-parse',c['commit']+':'+path)
assert 'assertion failed: !cause.is_retryable()' in Path('/tmp/sail-sdp-mutation-runtime-loss-counterexample.log').read_text()
for path in ['Cargo.lock','crates/sail-execution/Cargo.toml','crates/sail-common-datafusion/Cargo.toml']:
 assert git('rev-parse',c['base']+':'+path)==git('rev-parse',c['commit']+':'+path)
print('PASS exact owned-mutation interruption library/release/control qualification '+c['commit'])
