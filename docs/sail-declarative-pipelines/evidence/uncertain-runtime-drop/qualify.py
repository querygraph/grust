from pathlib import Path
import json,hashlib,subprocess
root=Path('/Users/alexy/src/sail-sdp-gate');label='uncertain-runtime-drop-qualified'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-sail-object-store-release/receipt.json').read_text());p=Path('/tmp/sail-sdp-uncertain-runtime-drop-public');public=json.loads((p/'receipt.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
assert g['sail_commit']==r['commit']==public['sail_commit']==c['commit']
assert g['outcome']==r['outcome']==public['outcome']=='passed'
for check in g['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert '38 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
assert r['build_exit']==r['test_exit']==0 and all(code is not None for code in r['load_worker_exit_codes'])
assert len(r['load_pids'])==len(r['load_worker_exit_codes'])==r['logical_cpus']==10
for pid in r['load_pids']:
 process=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
 assert process.returncode!=0 or '/usr/bin/yes' not in process.stdout
assert hashlib.sha256(Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
assert '38 passed; 0 failed' in Path('/tmp/sail-sdp-'+label+'-sail-object-store-release/test.log').read_text()
assert public['before']==public['after'] and public['remaining_listener_pids']==[] and public['server_exit_code'] is not None
assert public['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert public['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert hashlib.sha256(Path(public['cli_path']).read_bytes()).hexdigest()==public['cli_sha256']
control=json.loads(Path('/tmp/sail-sdp-nested-uncertain-abort-control-candidate.json').read_text())
path='crates/sail-object-store/src/layers/runtime_owned_effect_tests.rs'
a=git('show',control['commit']+':'+path)
b=git('show',c['commit']+':'+path).split('#[tokio::test]\nasync fn explicit_abort_after_uncertain_complete',1)[0].strip()
assert a==b
assert 'nested Drop aborted an uncertain publication' in Path('/tmp/sail-sdp-nested-uncertain-abort-control.log').read_text()
for path in ['Cargo.lock','crates/sail-object-store/Cargo.toml']:assert git('rev-parse',c['base']+':'+path)==git('rev-parse',c['commit']+':'+path)
print('PASS exact wrapper Drop library/release/public/control qualification '+c['commit'])
