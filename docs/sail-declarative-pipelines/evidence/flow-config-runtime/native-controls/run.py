from pathlib import Path
import hashlib,json,os,subprocess,tempfile
repo=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate');base=json.loads(Path('/tmp/sail-sdp-source-read-case-ready-candidate.json').read_text())['commit']
def git(*args,**kw):return subprocess.check_output(['git','-C',str(repo),*args],text=True,**kw).strip()
items=[('source-case-getter','crates/sail-plan/src/resolver/mod.rs','        self.source_read_case_sensitive\n            .unwrap_or(self.config.case_sensitive)','        self.config.case_sensitive'),('source-case-view','crates/sail-plan/src/resolver/query/read.rs','                    resolver.source_read_case_sensitive = self.source_read_case_sensitive;','')]
for label,path,old,new in items:
 s=git('show',base+':'+path)+'\n';assert s.count(old)==1;s=s.replace(old,new);blob=git('hash-object','-w','--stdin',input=s)
 fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
 try:
  git('read-tree',base,env=env);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Negative control: '+label)
 finally:Path(index).unlink(missing_ok=True)
 git('update-ref','refs/sdp-evidence/'+label,control)
 assert git('diff','--name-only',base,control)==path
 tests='crates/sail-plan/src/resolver/query/read_case_tests.rs';assert git('rev-parse',base+':'+tests)==git('rev-parse',control+':'+tests)
 subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
 log=Path('/tmp/sail-sdp-'+label+'-control.log')
 env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
 with log.open('w')as out:r=subprocess.run(['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','read_case_override'],cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-'+label+'-control.json').write_text(json.dumps({'base':base,'control':control,'path':path,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
 print(log.read_text()[-2200:],flush=True);assert r.returncode==101 and'0 passed; 2 failed'in log.read_text()
 subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
 print('PASS '+label+' unchanged0/2 control',flush=True)
