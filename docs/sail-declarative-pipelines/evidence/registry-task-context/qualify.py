from pathlib import Path
import json,hashlib,subprocess,textwrap
label='registry-task-context-final'
root='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit']
assert not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert [x['name'] for x in g['checks']]==['fmt','clippy','rust']
for check in g['checks']:
 assert check['exit_code']==0
 assert hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert '115 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
p=Path('/tmp/sail-sdp-'+label+'-sail-common-datafusion-release')
r=json.loads((p/'receipt.json').read_text())
assert r['commit']==c['commit'] and r['outcome']=='passed'
assert r['build_exit']==r['test_exit']==0
assert len(r['load_pids'])==r['logical_cpus'] and r['logical_cpus']>0
assert all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '115 passed; 0 failed;' in (p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
assert all(x.startswith('crates/sail-common-datafusion/src/task_resources_') for x in c['paths'])
old=git('show',c['base']+':crates/sail-common-datafusion/src/task_resources_context.rs')
body=textwrap.dedent(old.split('mod tests {\n',1)[1].rsplit('\n}',1)[0])
new=git('show',c['commit']+':crates/sail-common-datafusion/src/task_resources_context_tests.rs').split('\n#[path = "task_resources_registry_context_tests.rs"]',1)[0]
assert body.strip()==new.strip()
print('PASS exact context candidate, 115 library +115 optimized tests, joined load workers, original test extraction and unchanged dependency footprint '+c['commit'])
