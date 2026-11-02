from pathlib import Path
import hashlib,json,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='resolver-query-session-registry'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert [x['name']for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:assert x['exit_code']==0 and sha(x['log'])==x['sha256']
assert '42 passed; 0 failed;'in Path(g['checks'][-1]['log']).read_text()
r=json.loads(Path('/tmp/sail-sdp-resolver-helper-session-bypass-receipt.json').read_text());log=Path(r['log']).read_text()
assert r['fixed_commit']==c['commit'] and r['exit_code']==101 and sha(r['log'])==r['sha256']
assert '1 passed; 4 failed;'in log and log.count('session extension not found: task resource scope')==4
assert git('diff','--name-only',r['commit'],c['commit'])=='crates/sail-plan/src/resolver/session.rs'
path='crates/sail-plan/src/resolver/query/session_tests.rs';assert git('rev-parse',r['commit']+':'+path)==git('rev-parse',c['commit']+':'+path)
p=Path('/tmp/sail-sdp-'+label+'-sail-plan-release');r=json.loads((p/'receipt.json').read_text());assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert sha(r['binary'])==r['binary_sha256'] and '42 passed; 0 failed;'in(p/'test.log').read_text()
assert len(r['load_pids'])==r['logical_cpus']==len(r['load_worker_exit_codes']) and all(x is not None for x in r['load_worker_exit_codes'])
p=Path('/tmp/sail-sdp-resolver-query-session-public');r=json.loads((p/'receipt.json').read_text());assert r['sail_commit']==c['commit'] and r['outcome']=='passed' and r['before']==r['after']
assert r['server_exit_code']==0 and r['remaining_listener_pids']==[] and sha(r['cli_path'])==r['cli_sha256']
assert r['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
assert r['upstream']==dict(tests_run=67,failures=0,errors=0,skipped=0,server_spark_version='4.2.1')
for x in r['checks']:assert x['exit_code']==0 and sha(p/(x['name']+'.log'))==x['log_sha256']
for name,value in r['artifact_sha256'].items():assert sha(p/name)==value
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])and len(c['paths'])==9
assert git('diff',c['base'],c['commit'],'--','Cargo.lock','Cargo.toml')==''
print('PASS exact resolver helper Session, unchanged four-helper bypass, 42 library/optimized +300 public/67 upstream '+c['commit'])
