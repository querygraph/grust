from pathlib import Path
import json, os, subprocess, sys, tempfile
root='/Users/alexy/src/sail-pipelines-proposal'
c=json.loads(Path('/tmp/sail-sdp-'+sys.argv[1]+'-candidate.json').read_text())
def git(*args,**kw):
    return subprocess.check_output(['git','-C',root,*args],text=True,**kw).strip()
assert git('rev-parse','HEAD')==c['base']
fd,index=tempfile.mkstemp(prefix='sail-sdp-verify-index-');os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
    git('read-tree',c['base'],env=env)
    git('add',*c['paths'],env=env)
    assert git('write-tree',env=env)==git('rev-parse',c['commit']+'^{tree}')
finally:
    Path(index).unlink(missing_ok=True)
git('update-ref','refs/heads/work/spark-declarative-pipelines',c['commit'],c['base'])
git('read-tree',c['commit'])
print('Committed '+c['commit'])
print(git('status','--short'))
