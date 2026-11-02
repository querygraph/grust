from pathlib import Path
import hashlib,json,subprocess
label='procedure-factory-session';repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());p=Path('/tmp/sail-sdp-'+label+'-sail-plan-release');opt=json.loads((p/'receipt.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert 'test result: ok. 71 passed; 0 failed;' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert opt['commit']==c['commit'] and opt['outcome']=='passed' and opt['test_exit']==0;assert 'test result: ok. 4 passed; 0 failed;' in (p/'test.log').read_text();assert hashlib.sha256(Path(opt['binary']).read_bytes()).hexdigest()==opt['binary_sha256'];assert len(opt['load_worker_exit_codes'])==opt['logical_cpus'] and all(code is not None for code in opt['load_worker_exit_codes'])
path='crates/sail-plan/src/resolver/command/procedure.rs';old=git('show',c['base']+':'+path);new=git('show',c['commit']+':'+path);expected=old.replace('.infer_metadata(&self.ctx.state(),','.infer_metadata(self.provider_session().as_session(),').replace('''        let session = self.ctx.state();
        let plan = provider
            .plan_procedure(&session,''','''        let session = self.provider_session();
        let plan = provider
            .plan_procedure(session.as_session(),''');assert ''.join(new.split())==''.join(expected.split());assert new.count('self.ctx.state()')==1,'Keep the exact native analyzer path'
for kind,counts in [('factory',(2,2)),('metadata',(3,1))]:
 stem='/tmp/sail-sdp-procedure-'+kind+'-bypass';ctl=json.loads(Path(stem+'-receipt.json').read_text());assert ctl['base']==c['commit'] and ctl['exit_code']==101;log=Path(stem+'.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==ctl['log_sha256'];assert f'test result: FAILED. {counts[0]} passed; {counts[1]} failed;' in log.read_text()
 if kind=='factory':expected=new.replace('let session = self.provider_session();','let session = self.ctx.state();').replace('.plan_procedure(session.as_session(),','.plan_procedure(&session,')
 else:expected=new.replace('.infer_metadata(self.provider_session().as_session(), *info.clone())','.infer_metadata(&self.ctx.state(), *info.clone())')
 assert git('show',ctl['commit']+':'+path)==expected
 for test in c['paths']:
  if '/query/' in test:assert git('rev-parse',c['commit']+':'+test)==git('rev-parse',ctl['commit']+':'+test)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
print('PASS exact procedure routes/71 libraries/4 optimized/independent factory and metadata controls; native analyzer unchanged')
