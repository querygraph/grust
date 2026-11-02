from pathlib import Path
import json,os,subprocess,sys,tempfile
root='/Users/alexy/src/grust-sdp'
def git(*args,**kw):return subprocess.check_output(['git','-C',root,*args],text=True,**kw).strip()
prepare=sys.argv[1]=='prepare'
p=Path('/tmp/sail-sdp-evidence-candidate.json')
c={'base':git('rev-parse','HEAD'),'paths':sys.argv[3:] or ['docs/sail-declarative-pipelines','codex-to-codex.md']} if prepare else json.loads(p.read_text())
assert git('rev-parse','HEAD')==c['base']
fd,index=tempfile.mkstemp(prefix='sdp-doc-index-');os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',c['base'],env=env);git('add',*c['paths'],env=env);tree=git('write-tree',env=env)
 if prepare:
  c['commit']=git('commit-tree',tree,'-p',c['base'],'-m',sys.argv[2]);p.write_text(json.dumps(c,indent=2)+'\n')
  subprocess.run(['git','-C','/Users/alexy/src/grust-sdp-review-gate','checkout','--detach',c['commit']],check=True)
 else:
  assert tree==git('rev-parse',c['commit']+'^{tree}')
  git('update-ref','refs/heads/work/sail-declarative-pipelines',c['commit'],c['base']);git('read-tree',c['commit']);git('sparse-checkout','reapply')
  assert not git('status','--porcelain','--',*c['paths'])
  print('Committed '+c['commit'])
finally:Path(index).unlink(missing_ok=True)
