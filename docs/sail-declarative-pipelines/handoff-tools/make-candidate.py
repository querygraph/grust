from pathlib import Path
import json, os, subprocess, sys, tempfile
root=Path('/Users/alexy/src/sail-pipelines-proposal')
label,message,*paths=sys.argv[1:]
def git(*args,**kw):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,**kw).strip()
base=git('rev-parse','HEAD')
fd,index=tempfile.mkstemp(prefix='sail-sdp-index-');os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
    git('read-tree',base,env=env)
    git('add',*paths,env=env)
    tree=git('write-tree',env=env)
    commit=git('commit-tree',tree,'-p',base,'-m',message)
finally:
    Path(index).unlink(missing_ok=True)
Path('/tmp/sail-sdp-'+label+'-candidate.json').write_text(json.dumps({'base':base,'commit':commit,'paths':paths},indent=2)+'\n')
subprocess.run(['git','-C','/Users/alexy/src/sail-sdp-gate','checkout','--detach',commit],check=True)
print(commit)
