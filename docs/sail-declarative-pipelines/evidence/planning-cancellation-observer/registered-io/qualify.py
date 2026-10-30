from pathlib import Path
import hashlib,json,subprocess
label='preparation-registered-io-qualified';root='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
p='crates/sail-common-datafusion/src/task_resources_cancellation_tests.rs'
assert git('diff','--name-only',c['base'],c['commit'])==p
before=git('show',c['base']+':'+p);after=git('show',c['commit']+':'+p)
assert after.startswith(before) and 'cancelled_borrowed_waiter_keeps_registered_io_owned_until_settlement' in after[len(before):]
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '121 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
p=Path('/tmp/sail-sdp-'+label+'-sail-common-datafusion-release');r=json.loads((p/'receipt.json').read_text())
assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '121 passed; 0 failed;' in (p/'test.log').read_text()
assert 'cancelled_borrowed_waiter_keeps_registered_io_owned_until_settlement ... ok' in (p/'test.log').read_text()
print('PASS exact registered-I/O/borrowed-waiter regression, unchanged production and prior tests, 121 library/optimized tests '+c['commit'])
