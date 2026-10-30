from pathlib import Path
import hashlib,json,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-binding-root-integration-fields';offer='d77fc47958641933e84577bfa88e3be5cfbd9471';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
assert git('rev-parse','HEAD')==c['base']
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 96 passed; 0 failed;' in log
for path in c['paths']:
 current=git('show',c['commit']+':'+path)
 if path.endswith('/mod.rs'):
  assert current==git('show',c['base']+':'+path).replace('pub(super) mod intent;','pub(super) mod binding;\npub(super) mod intent;')
 elif path.endswith('/binding.rs'):
  annotation='    #[cfg_attr(\n        test,\n        expect(dead_code, reason = "read by the admission integration unit")\n    )]\n';assert current.count(annotation)==2
  assert current.replace(annotation,'')==git('show',offer+':'+path)
 else:assert current==git('show',offer+':'+path)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS exact binding import source/gates (134+96); only two temporary test-only field expectations differ from offer')
