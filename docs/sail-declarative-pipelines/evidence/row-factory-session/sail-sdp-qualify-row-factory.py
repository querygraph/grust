from pathlib import Path
import hashlib,json,subprocess
label='row-factory-session';repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());p=Path('/tmp/sail-sdp-'+label+'-sail-plan-release');opt=json.loads((p/'receipt.json').read_text());control=json.loads(Path('/tmp/sail-sdp-row-factory-session-bypass-receipt.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert 'test result: ok. 63 passed; 0 failed;' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert opt['commit']==c['commit'] and opt['outcome']=='passed' and opt['test_exit']==0;assert 'test result: ok. 8 passed; 0 failed;' in (p/'test.log').read_text();assert hashlib.sha256(Path(opt['binary']).read_bytes()).hexdigest()==opt['binary_sha256'];assert len(opt['load_worker_exit_codes'])==opt['logical_cpus'] and all(code is not None for code in opt['load_worker_exit_codes'])
assert control['base']==c['commit'] and control['exit_code']==101;log=Path('/tmp/sail-sdp-row-factory-session-bypass.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==control['log_sha256'];assert 'test result: FAILED. 4 passed; 4 failed;' in log.read_text()
for path in c['paths']:
 if '/query/' in path:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse',control['commit']+':'+path)
 else:
  assert git('rev-parse',c['base']+':'+path)==git('rev-parse',control['commit']+':'+path)
  old=git('show',c['base']+':'+path);new=git('show',c['commit']+':'+path)
  if path.endswith('/merge.rs'):expected=old.replace('let session_state = self.ctx.state();','let session = self.provider_session();').replace('                &session_state,','                session.as_session(),')
  else:expected=old.replace('&self.ctx.state()','self.provider_session().as_session()')
  assert new==expected,path
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
print('PASS exact four row-factory routes/63 libraries/8 optimized/unchanged4fail4legacy controls; no fresh CLI claim')
