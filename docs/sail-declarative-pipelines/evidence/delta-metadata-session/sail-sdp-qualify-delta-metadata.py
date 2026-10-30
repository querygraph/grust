from pathlib import Path
import hashlib,json,subprocess
label='delta-metadata-session-counts';repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());p=Path('/tmp/sail-sdp-'+label+'-sail-plan-release');opt=json.loads((p/'receipt.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert 'test result: ok. 67 passed; 0 failed;' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert opt['commit']==c['commit'] and opt['outcome']=='passed' and opt['test_exit']==0;assert 'test result: ok. 4 passed; 0 failed;' in (p/'test.log').read_text();assert hashlib.sha256(Path(opt['binary']).read_bytes()).hexdigest()==opt['binary_sha256'];assert len(opt['load_worker_exit_codes'])==opt['logical_cpus'] and all(code is not None for code in opt['load_worker_exit_codes'])
path='crates/sail-plan/src/resolver/command/delta.rs';old=git('show',c['base']+':'+path);new=git('show',c['commit']+':'+path);assert old.count('.infer_metadata(&self.ctx.state(),')==2;assert ''.join(new.split())==''.join(old.replace('.infer_metadata(&self.ctx.state(),','.infer_metadata(self.provider_session().as_session(),').split())
for kind,arg in [('path','source_info'),('catalog','source')]:
 stem='/tmp/sail-sdp-delta-'+kind+'-metadata-bypass';ctl=json.loads(Path(stem+'-receipt.json').read_text());assert ctl['base']==c['commit'] and ctl['exit_code']==101;log=Path(stem+'.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==ctl['log_sha256'];assert 'test result: FAILED. 3 passed; 1 failed;' in log.read_text();assert 'delta_'+kind+'_metadata_uses_selected_session ... FAILED' in log.read_text()
 expected=new.replace('.infer_metadata(self.provider_session().as_session(), '+arg+')','.infer_metadata(&self.ctx.state(), '+arg+')');assert git('show',ctl['commit']+':'+path)==expected
 for test in c['paths']:
  if '/query/' in test:assert git('rev-parse',c['commit']+':'+test)==git('rev-parse',ctl['commit']+':'+test)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
print('PASS exact Delta callbacks/67 libraries/4 optimized/two independent unchanged metadata-admission controls')
