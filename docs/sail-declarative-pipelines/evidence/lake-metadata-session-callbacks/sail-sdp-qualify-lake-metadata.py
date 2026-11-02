from pathlib import Path
import hashlib,json,subprocess
label='lake-metadata-command-session-result';repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());optpath=Path('/tmp/sail-sdp-'+label+'-sail-plan-release');opt=json.loads((optpath/'receipt.json').read_text());ctrl=json.loads(Path('/tmp/sail-sdp-lake-metadata-session-bypass-receipt.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
assert git('rev-parse','HEAD')==c['base']
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert 'test result: ok. 55 passed; 0 failed;' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
assert opt['commit']==c['commit'] and opt['outcome']=='passed' and opt['test_exit']==0
assert 'test result: ok. 6 passed; 0 failed;' in (optpath/'test.log').read_text()
assert hashlib.sha256(Path(opt['binary']).read_bytes()).hexdigest()==opt['binary_sha256']
assert len(opt['load_worker_exit_codes'])==opt['logical_cpus'] and all(code is not None for code in opt['load_worker_exit_codes'])
assert ctrl['base']==c['commit'] and ctrl['exit_code']==101
log=Path('/tmp/sail-sdp-lake-metadata-session-bypass.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==ctrl['log_sha256']
assert 'test result: FAILED. 3 passed; 3 failed;' in log.read_text()
for path in c['paths']:
 if '/query/' in path:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse',ctrl['commit']+':'+path)
 else:assert git('rev-parse',c['base']+':'+path)==git('rev-parse',ctrl['commit']+':'+path)
print('PASS exact metadata Session source/gates/optimized workers/unchanged bypass; no fresh public CLI claim')
