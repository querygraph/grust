import subprocess,sys
repo,head,tree=sys.argv[1:]
def git(*args):return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
assert git('rev-parse','HEAD')==head
assert git('write-tree')==tree
assert subprocess.run(['git','-C',repo,'diff','--quiet']).returncode==0
assert not git('ls-files','--others','--exclude-standard')
