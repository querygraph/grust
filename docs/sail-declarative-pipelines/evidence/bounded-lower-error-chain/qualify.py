from pathlib import Path
import json,hashlib,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-lower-error-chain';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
for path in c['paths']:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse','dea394efb:'+path)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 131 passed; 0 failed;' in log;assert 'lower_errors_expose_their_typed_causes_through_the_standard_chain ... ok' in log
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS exact typed lower-error source/two blobs,134+131 libraries,provider downcast chain')
