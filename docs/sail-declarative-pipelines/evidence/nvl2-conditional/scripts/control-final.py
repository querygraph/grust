from pathlib import Path
import hashlib,json,os,subprocess,tempfile
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
def git(*a,**kw):return subprocess.check_output(['git','-C',R,*a],text=True,**kw).strip()
c=json.load(open('/tmp/sail-sdp-nvl2-conditional-candidate.json'));base=c['commit'];r=json.load(open('/tmp/sail-sdp-nvl2-conditional-gate.json'));assert r['outcome']=='passed' and r['sail_commit']==base
path='crates/sail-plan/src/function/scalar/conditional.rs';test_path='crates/sail-plan/src/function/scalar/conditional/tests.rs'
s=git('show',base+':'+path);a=s.index('        // The tested value is not part');b=s.index('\n    }',a);s=s[:a]+'        return Ok(expr_fn::nvl2(value, then_value, else_value));'+s[b:]
blob=git('hash-object','-w','--stdin',input=s+'\n');fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
try:
 env={**os.environ,'GIT_INDEX_FILE':index};git('read-tree',base,env=env);git('update-index','--cacheinfo','100644,'+blob+','+path,env=env);tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Control: restore ordinary NVL2 UDF lowering')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/nvl2-conditional-final-control',control)
assert git('diff','--name-only',base,control)==path
assert git('rev-parse',base+':'+test_path)==git('rev-parse',control+':'+test_path)
subprocess.run(['git','-C',G,'checkout','--detach',control],check=True)
command=['cargo','+1.98.1','test','-p','sail-plan','--lib','--locked','function::scalar::conditional::tests']
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':R+'/.venv/bin/python','PYTHONPATH':R+'/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':R+'/.venv'}
log=Path('/tmp/sail-sdp-nvl2-control-final.log')
with log.open('x') as out:p=subprocess.run(command,cwd=G,env=env,stdout=out,stderr=subprocess.STDOUT)
Path('/tmp/sail-sdp-nvl2-control-final.json').write_text(json.dumps({'base':base,'control':control,'path':path,'test_path':test_path,'test_blob':git('rev-parse',base+':'+test_path),'command':command,'exit_code':p.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},indent=2)+'\n')
assert p.returncode==101 and '0 passed; 2 failed;' in log.read_text(),log.read_text()[-3000:]
subprocess.run(['git','-C',G,'checkout','--detach',base],check=True)
print('PASS production-only control: unchanged tests 0/2')
