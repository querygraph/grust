from pathlib import Path
import json,hashlib,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='admission-signature-fixtures';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert len(c['paths'])==1 and c['paths'][0].endswith('/admission_tests.rs')
p=c['paths'][0];assert git('show',c['commit']+':'+p).split('\n\n',1)[1]==git('show','b32e4b67825f46de91290cd40e3b40fb80b9fbc2:'+p).split('\n\n',1)[1]
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 114 passed; 0 failed;' in log
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
print('PASS exact test-only signature fixture import and 134+114 libraries; no execution support verdict')
