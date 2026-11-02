from pathlib import Path
import json,hashlib,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='scoped-native-analyzer';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());ctl=json.loads(Path('/tmp/sail-sdp-native-analyzer-optimizer-control-receipt.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 136 passed; 0 failed;' in log and 'test result: ok. 71 passed; 0 failed;' in log
assert ctl['base']==c['commit'] and ctl['exit_code']==101;p=Path('/tmp/sail-sdp-native-analyzer-optimizer-control.log');assert hashlib.sha256(p.read_bytes()).hexdigest()==ctl['log_sha256'] and 'test result: FAILED. 1 passed; 1 failed;' in p.read_text()
path='crates/sail-common-datafusion/src/session/scoped/analyzer_tests.rs';assert git('rev-parse',c['commit']+':'+path)==git('rev-parse',ctl['commit']+':'+path)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
print('PASS exact captured native analyzer:136+71 libraries,typed cause preserved,unchanged optimizer substitution fails')
