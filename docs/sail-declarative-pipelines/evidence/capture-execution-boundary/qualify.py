from pathlib import Path
import json,hashlib,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='capture-transfer-boundary';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());p=Path('/tmp/sail-sdp-'+label+'-sail-execution-release');opt=json.loads((p/'receipt.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths']);assert all('/local/' in path and path.endswith('tests.rs') for path in c['paths'])
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 222 passed; 0 failed;' in log;assert 'legacy_bound_execution_recaptures_authority_after_scoped_planning ... ok' in log
assert opt['commit']==c['commit'] and opt['outcome']=='passed' and opt['test_exit']==0;assert 'test result: ok. 1 passed; 0 failed;' in (p/'test.log').read_text();assert hashlib.sha256(Path(opt['binary']).read_bytes()).hexdigest()==opt['binary_sha256'];assert len(opt['load_worker_exit_codes'])==opt['logical_cpus'] and all(code is not None for code in opt['load_worker_exit_codes'])
print('PASS test-only capture/execution boundary:134+222 libraries,one optimized case,all load workers joined; no API/production change')
