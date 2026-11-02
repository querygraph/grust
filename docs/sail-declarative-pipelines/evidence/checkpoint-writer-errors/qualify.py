from pathlib import Path
import hashlib,json,subprocess
import xml.etree.ElementTree as ET
label='checkpoint-writer-errors-qualified'; root='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
for x in g['checks']:
 assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
log=Path(g['checks'][-1]['log']).read_text()
for count in [117,202]:assert str(count)+' passed; 0 failed;' in log
control=json.loads(Path('/tmp/sail-sdp-checkpoint-writer-error-control-receipt.json').read_text())
assert control['exit_code']==101
text=Path(control['log']).read_text();assert hashlib.sha256(Path(control['log']).read_bytes()).hexdigest()==control['sha256']
assert '0 passed; 4 failed;' in text and text.count('published checkpoint became retryable:')==4
paths=['crates/sail-execution/src/lib.rs','crates/sail-execution/src/checkpoint_writer_error_tests.rs']
assert set(git('diff','--name-only',c['base'],control['commit']).splitlines())==set(paths)
for p in paths:assert git('rev-parse',control['commit']+':'+p)==git('rev-parse',c['commit']+':'+p)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
baseline=json.loads(Path('/tmp/sail-sdp-checkpoint-error-ordinary-baseline-receipt.json').read_text())
assert baseline['exit_code']==0
assert git('rev-parse',baseline['commit']+':crates/sail-common-datafusion/src/error.rs')==git('rev-parse',c['base']+':crates/sail-common-datafusion/src/error.rs')
assert git('diff','--name-only',c['base'],baseline['commit'])=='crates/sail-common-datafusion/src/error/tests.rs'
b=Path(baseline['log']).read_bytes();assert hashlib.sha256(b).hexdigest()==baseline['sha256']
assert b.count(b'BASELINE actual=')==4 and b'1 passed; 0 failed;' in b

for package,count in [('sail-common-datafusion',117),('sail-execution',4)]:
 p=Path('/tmp/sail-sdp-'+label+'-'+package+'-release');r=json.loads((p/'receipt.json').read_text())
 assert r['commit']==c['commit'] and r['outcome']=='passed' and r['build_exit']==r['test_exit']==0
 assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
 assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
 assert str(count)+' passed; 0 failed;' in (p/'test.log').read_text()
p=Path('/tmp/sail-sdp-checkpoint-writer-errors-public');r=json.loads((p/'receipt.json').read_text())
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
assert r['before']==r['after'] and r['before']['head']==c['commit']
assert r['server_exit_code']==0 and r['remaining_listener_pids']==[]
assert hashlib.sha256(Path(r['cli_path']).read_bytes()).hexdigest()==r['cli_sha256']
for path,digest in r['artifact_sha256'].items():
 assert hashlib.sha256((p/path).read_bytes()).hexdigest()==digest
x=ET.parse(p/'pytest.xml').getroot().find('testsuite')
assert (x.get('tests'),x.get('failures'),x.get('errors'),x.get('skipped'))==('300','0','0','0')
u=json.loads((p/'upstream.json').read_text());assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0
assert u['server_spark_version']=='4.2.1'
print('PASS exact unchanged four-case writer control, fixed library/optimized/public gates '+c['commit'])
