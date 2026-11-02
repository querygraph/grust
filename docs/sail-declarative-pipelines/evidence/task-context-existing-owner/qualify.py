from pathlib import Path
import hashlib,json,subprocess
label='task-context-existing-owner';root='/Users/alexy/src/sail-sdp-gate'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());assert g['outcome']=='passed' and g['sail_commit']==c['commit']
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '125 passed; 0 failed;' in Path(g['checks'][-1]['log']).read_text()
p=Path('/tmp/sail-sdp-'+label+'-sail-common-datafusion-release');r=json.loads((p/'receipt.json').read_text());assert r['commit']==c['commit'] and r['outcome']=='passed' and r['test_exit']==r['build_exit']==0
assert len(r['load_pids'])==r['logical_cpus']>0 and all(x is not None for x in r['load_worker_exit_codes'])
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '125 passed; 0 failed;' in (p/'test.log').read_text()
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths']) and len(c['paths'])==2
print('PASS exact existing-owner context helper, 125 library/optimized tests '+c['commit'])
