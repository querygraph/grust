from pathlib import Path
from datetime import datetime,timezone
import json,os,tempfile,hashlib,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='scoped-native-analyzer';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());path='crates/sail-common-datafusion/src/session/scoped.rs'
def git(*a,**kw):return subprocess.check_output(['git','-C',repo,*a],text=True,**kw).strip()
source=git('show',c['commit']+':'+path);start=source.index('    pub fn analyze(');end=source.index('\n    }',start)+len('\n    }');source=source[:start]+'''    pub fn analyze(&self, plan: LogicalPlan) -> Result<LogicalPlan> {
        self.optimize(&plan)
    }'''+source[end:]+'\n'
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',c['commit'],env=env);blob=git('hash-object','-w','--stdin',input=source);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',c['commit'],'-m','Substitute optimization for native-only analysis with unchanged tests')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/native-analyzer-optimizer-control',commit);subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True);Path('/tmp/sail-sdp-native-analyzer-optimizer-control-candidate.json').write_text(json.dumps({'base':c['commit'],'commit':commit,'paths':[path]},indent=2)+'\n')
command=['cargo','+1.98.1','test','-p','sail-common-datafusion','--lib','--locked','session::scoped::analyzer_tests'];env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'};log=Path('/tmp/sail-sdp-native-analyzer-optimizer-control.log')
with log.open('w') as output:result=subprocess.run(command,cwd=gate,env=env,stdout=output,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-native-analyzer-optimizer-control-receipt.json').write_text(json.dumps({'commit':commit,'base':c['commit'],'command':command,'exit_code':result.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'recorded_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n');assert result.returncode==101 and 'test result: FAILED. 1 passed; 1 failed;' in log.read_text(),log.read_text()[-7000:];assert 'native_analysis_uses_captured_config_without_optimization ... FAILED' in log.read_text();subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True);print('PASS unchanged analyzer-only control detects optimizer substitution')
