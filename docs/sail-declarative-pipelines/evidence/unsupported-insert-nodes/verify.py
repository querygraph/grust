from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit'];assert not s['full_conformance'] and not s['inventory_changed']
g=read('native/sail-sdp-unsupported-insert-nodes-01-gate.json');assert g['sail_commit']==commit and g['outcome']=='passed'
for c in g['checks']:assert c['exit_code']==0 and sha(E/'native'/Path(c['log']).name)==c['sha256']
assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',(E/'native/sail-sdp-unsupported-insert-nodes-01-rust.log').read_text())))==[4,9,61,123,204]
syntax=read('native/sail-sdp-unsupported-insert-nodes-01-syntax.json');assert syntax['exit_code']==0 and syntax['sail_commit']==commit and sha(E/'native/sail-sdp-unsupported-insert-nodes-01-syntax.log')==syntax['log_sha256']
assert set(git('diff','--name-only',commit+'^',commit).decode().splitlines())=={'crates/sail-sql-analyzer/src/pipeline.rs','crates/sail-sql-analyzer/src/pipeline/tests/unsupported.rs','python/pysail/tests/spark/pipelines/test_unsupported_insert_nodes.py'}
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
records=[]
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r);assert r['pytest_exit_code']==0 and not r['remaining_listeners'] and r['version']=='4.2.1'
 assert r['test_sha256']==hashlib.sha256(git('show',commit+':python/pysail/tests/spark/pipelines/test_unsupported_insert_nodes.py')).hexdigest()
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==7 and all(not list(c)for c in cases)
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256']
c=read('reference-comparison.json');assert len(c)==16 and sum(x['matched']for x in c)==14==s['reference_matches']
for a,b,x in zip(records[0]['cases'],records[1]['cases'],c):
 assert a['sql']==b['sql']==x['sql'] and x['matched']==all(a.get(k)==b.get(k)for k in ['outcome','error_type','condition','sql_state','parameters'])
assert [x['label']for x in c if not x['matched']]==['flow-replace-where','flow-replace-using']
c=read('control.json');assert c['base']==commit and c['exit_code']==101 and sha(E/'control.log')==c['log_sha256'] and '0 passed; 1 failed;'in(E/'control.log').read_text()
assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS unsupported INSERT401native+syntax/300+67/paired7/control;14of16 reference vectors;REPLACE backlog retained')
