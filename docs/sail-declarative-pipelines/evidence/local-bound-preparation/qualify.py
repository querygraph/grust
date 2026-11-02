from pathlib import Path
import hashlib,json,re,subprocess
root='/Users/alexy/src/sail-sdp-gate'; label='local-bound-preparation-qualified'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());commit=c['commit']
assert git('rev-parse','HEAD')==commit and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==commit and g['outcome']=='passed'
assert [x['name']for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:assert x['exit_code']==0 and sha(x['log'])==x['sha256']
log=Path(g['checks'][-1]['log']).read_text()
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',log)==['125','221','29']
r=json.loads(Path('/tmp/sail-sdp-local-preparation-admission-control-receipt.json').read_text())
assert r['fixed_commit']==commit and r['exit_code']==101 and sha(r['log'])==r['sha256']
s=Path(r['log']).read_text();assert '0 passed; 1 failed;'in s and re.search(r'left: 0\s+right: 1',s)
assert git('diff','--name-only',r['commit'],commit)=='crates/sail-execution/src/job_runner/local.rs'
for test in ['tests.rs','preparation_tests.rs']:
 path='crates/sail-execution/src/job_runner/local/'+test
 assert git('rev-parse',r['commit']+':'+path)==git('rev-parse',commit+':'+path)
p=Path('/tmp/sail-sdp-'+label+'-sail-execution-release');r=json.loads((p/'receipt.json').read_text())
assert r['commit']==commit and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus']==len(r['load_worker_exit_codes']) and all(x is not None for x in r['load_worker_exit_codes'])
assert sha(r['binary'])==r['binary_sha256'] and '16 passed; 0 failed;'in(p/'test.log').read_text()
p=Path('/tmp/sail-sdp-local-bound-preparation-public');r=json.loads((p/'receipt.json').read_text())
assert r['sail_commit']==commit and r['outcome']=='passed' and r['before']==r['after']
assert r['server_exit_code']==0 and r['remaining_listener_pids']==[] and sha(r['cli_path'])==r['cli_sha256']
assert r['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
assert r['upstream']==dict(tests_run=67,failures=0,errors=0,skipped=0,server_spark_version='4.2.1')
for x in r['checks']:assert x['exit_code']==0 and sha(p/(x['name']+'.log'))==x['log_sha256']
for name,value in r['artifact_sha256'].items():assert sha(p/name)==value
assert set(git('diff','--name-only',c['base'],commit).splitlines())==set(c['paths'])
assert git('diff',c['base'],commit,'--','Cargo.lock','Cargo.toml')==''
old=git('show',c['base']+':crates/sail-execution/src/job_runner/local/tests.rs')
new=git('show',commit+':crates/sail-execution/src/job_runner/local/tests.rs')
assert new==old+'\n\n#[path = "preparation_tests.rs"]\nmod preparation;'
print('PASS exact bound local preparation: 375 library, 16 optimized, unchanged admission control, 300 public +67 upstream; '+commit)
