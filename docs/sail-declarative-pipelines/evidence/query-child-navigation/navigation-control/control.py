from pathlib import Path
import hashlib,json,os,subprocess,tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
c=json.loads(Path('/tmp/sail-sdp-query-child-navigation-fixed-candidate.json').read_text());base=c['commit'];path='crates/sail-common/src/spec/query_children.rs'
def git(*args,**kw):return subprocess.check_output(['git','-C',str(root),*args],text=True,**kw).strip()
s=git('show',base+':'+path)+'\n'
old='            N::Filter { input, condition } => {\n                visitor(QueryChild::Expression(condition))?;\n                visitor(QueryChild::Query(input))\n            }'
assert s.count(old)==1
s=s.replace(old,'            N::Filter { input, condition } => {\n                visitor(QueryChild::Query(input))?;\n                visitor(QueryChild::Expression(condition))\n            }')
blob=git('hash-object','-w','--stdin',input=s)
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);git('update-index','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env);control=git('commit-tree',tree,'-p',base,'-m','Negative control: visit filter input before expression')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp-evidence/query-child-navigation',control)
assert git('diff','--name-only',base,control)==path
for p in ['crates/sail-common/src/spec/query_child_tests.rs']:
 assert git('rev-parse',base+':'+p)==git('rev-parse',control+':'+p)
subprocess.run(['git','-C',str(gate),'checkout','--detach',control],check=True)
log=Path('/tmp/sail-sdp-query-child-control.log')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv','PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages'}
with log.open('w')as out:r=subprocess.run(['cargo','+1.98.1','test','-p','sail-common','--lib','--locked','spec::query_children::tests'],cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
report={'base':base,'control':control,'path':path,'exit_code':r.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
Path('/tmp/sail-sdp-query-child-control.json').write_text(json.dumps(report,indent=2)+'\n')
print(log.read_text()[-5000:],flush=True)
assert r.returncode==101 and '4 passed; 1 failed' in log.read_text()
subprocess.run(['git','-C',str(gate),'checkout','--detach',base],check=True)
print('PASS unchanged-test negative control4pass/1fail; restored positive source '+base,flush=True)
