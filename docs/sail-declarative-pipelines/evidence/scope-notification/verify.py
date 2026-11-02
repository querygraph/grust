from pathlib import Path
import hashlib,json,re,subprocess,sys
root=Path(sys.argv[1])/'docs/sail-declarative-pipelines/evidence'
repo='/Users/alexy/src/sail-pipelines-proposal'
for label,count,stress in [('scope-notification',87,9),('managed-stream',99,12)]:
 p=root/label
 manifest=json.loads((p/'provenance.json').read_text())
 expected={f['path'] for f in manifest['files']}|{'provenance.json'}
 assert expected=={f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file()}
 for f in manifest['files']:
  data=(p/f['path']).read_bytes()
  assert len(data)==f['bytes'] and hashlib.sha256(data).hexdigest()==f['sha256'],f['path']
 c=json.loads((p/'candidate.json').read_text());g=json.loads((p/'gate.json').read_text());r=json.loads((p/'release/receipt.json').read_text())
 assert c['commit']==g['sail_commit']==r['commit']==manifest['sail_commit']
 assert g['outcome']==r['outcome']=='passed'
 assert len(g['checks'])==3 and all(x['exit_code']==0 for x in g['checks'])
 for check in g['checks']:
  assert hashlib.sha256((p/(check['name']+'.log')).read_bytes()).hexdigest()==check['sha256']
 assert re.search(rf'test result: ok\. {count} passed; 0 failed;', (p/'rust.log').read_text())
 assert re.search(rf'test result: ok\. {stress} passed; 0 failed;', (p/'release/test.log').read_text())
 assert r['build_exit']==r['test_exit']==0
 assert len(r['load_pids'])==len(r['load_worker_exit_codes'])==r['logical_cpus']
 assert all(isinstance(x,int) for x in r['load_worker_exit_codes'])
 for line in (p/'release/build.jsonl').read_text().splitlines():json.loads(line)
 patch=subprocess.check_output(['git','-C',repo,'diff','--binary',c['base'],c['commit']])
 assert patch==(p/'commit.patch').read_bytes()
 print('PASS lifecycle evidence '+label+' '+c['commit'])
p=root/'scope-notification/baseline-control';r=json.loads((p/'receipt.json').read_text())
assert r['exit_code']==101
log=(p/'test.log').read_bytes()
assert hashlib.sha256(log).hexdigest()==r['test_log_sha256']
assert b'1 failed' in log and b'assertion failed: !watcher.lock_held.load(Ordering::SeqCst)' in log
assert subprocess.check_output(['git','-C',repo,'diff','--name-only',r['base'],r['commit']],text=True).splitlines()==['crates/sail-common-datafusion/src/task_resources_tests.rs']
assert subprocess.check_output(['git','-C',repo,'diff',r['base'],r['commit']])==(p/'control.patch').read_bytes()
print('PASS retained failure on unchanged resource-scope production source')
