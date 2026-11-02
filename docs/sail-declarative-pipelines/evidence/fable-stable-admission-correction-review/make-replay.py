from pathlib import Path
import json,os,subprocess,tempfile
repo='/Users/alexy/src/sail-pipelines-proposal';base='8f953dbf02fea36565ae032a4c3087eaf39e0f61';old='ca2038b94f631a881a089eb691815881b4df210b';path='crates/sail-spark-connect/src/pipelines/streaming/admission.rs'
def git(*args,**kwargs):return subprocess.check_output(['git','-C',repo,*args],text=True,**kwargs).strip()
s=git('show',base+':'+path);original=git('show',old+':'+path);a=original.index('    fn check_stable_clock');b=original.index('    #[test]\n    fn a_volatile_expression',a);fixture=original[a:b]
assert s.endswith('}');s=s[:-1]+'\n    mod codex_replay {\n        use super::*;\n'+fixture+'    }\n}\n'
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=s);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',base,'-m','Replay unchanged independent clock fixtures against corrected admission')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/stable-admission-correction-replay',commit)
Path('/tmp/sail-sdp-stable-admission-correction-replay-candidate.json').write_text(json.dumps({'base':base,'commit':commit,'fixture_source':old,'paths':[path],'fixture_sha256':__import__('hashlib').sha256(fixture.encode()).hexdigest()},indent=2)+'\n')
Path('/tmp/sail-sdp-stable-admission-correction-replay.patch').write_text(git('diff',base,commit)+'\n');print(commit)
