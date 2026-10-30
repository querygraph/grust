from pathlib import Path
import json,hashlib,subprocess,tomllib
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-lowerer-root-integration';offer='40b979ec98a5d917b8c8555936629eb02404595f';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
for path in c['paths']:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse',offer+':'+path),path
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
a=tomllib.loads(git('show',c['base']+':Cargo.lock'));b=tomllib.loads(git('show',c['commit']+':Cargo.lock'));packages=[p for p in a['package'] if p['name']=='sail-spark-connect'];assert len(packages)==1 and 'sha2' not in packages[0]['dependencies'];packages[0]['dependencies'].append('sha2');packages[0]['dependencies'].sort();assert a==b,'Only the consuming package dependency edge may change'
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 130 passed; 0 failed;' in log;assert log.count('test pipelines::streaming::lower::tests::')==13
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS exact lowerer five offered blobs, one existing sha2 consumer edge, 134+130 libraries/13 lowerer cases')
