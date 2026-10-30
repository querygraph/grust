from pathlib import Path
import hashlib,json,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-inline-udtf-guard';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
for path in c['paths']:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse','d1f2fd565:'+path)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 117 passed; 0 failed;' in log
replay=json.loads(Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay-receipt.json').read_text());assert replay['exit_code']==0 and replay['fixture_source']=='8907014d7c51ca0ffc8fc73f2ef5e526552287e0'
p=Path('/tmp/sail-sdp-dynamic-udtf-guard-correction-replay.log');assert hashlib.sha256(p.read_bytes()).hexdigest()==replay['log_sha256'] and 'test result: ok. 2 passed; 0 failed;' in p.read_text()
original=git('show',replay['fixture_source']+':'+replay['paths'][0])+'\n';fixture=original[original.index('fn inline_table_function'):];assert hashlib.sha256(fixture.encode()).hexdigest()==replay['fixture_sha256'] and fixture in git('show',replay['commit']+':'+replay['paths'][0])
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS exact UDTF guard source/134+117 libraries/unchanged2-case correction replay')
