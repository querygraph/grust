from pathlib import Path
import json, subprocess
c=json.loads(Path('/tmp/sail-sdp-sql-gold-candidate.json').read_text());gate='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',gate,*args],text=True)
assert git('rev-parse','HEAD').strip()==c['commit']
assert not git('status','--porcelain').strip()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
changes=0
for p in c['paths']:
 a=json.loads(git('show',c['base']+':'+p));b=json.loads(git('show',c['commit']+':'+p))
 assert len(a['tests'])==len(b['tests'])
 for old,new in zip(a['tests'],b['tests']):
  assert old['input']==new['input']
  assert old.get('exception')==new.get('exception')
  changes+=old['output']!=new['output']
assert changes==8
log=Path('/tmp/sail-sdp-sql-gold-rust.log').read_text()
assert '31 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out' in log
subprocess.run(['git','-C',gate,'diff','--check',c['base'],c['commit']],check=True)
print('PASS detached SQL golden gate '+c['commit']+'; 31 tests; 8 reviewed expectations; inputs/exceptions unchanged')
