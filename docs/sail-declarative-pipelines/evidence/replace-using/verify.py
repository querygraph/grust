from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit'];assert not s['full_conformance'] and not s['inventory_changed']
for n in ['01','02']:
 g=read('native-'+n+'/sail-sdp-replace-using-'+n+'-gate.json')
 for c in g['checks']:assert sha(E/('native-'+n)/Path(c['log']).name)==c['sha256']
 if n=='02':assert g['sail_commit']==commit and g['outcome']=='passed' and all(c['exit_code']==0 for c in g['checks'])
 else:assert g['outcome']=='passed' and all(c['exit_code']==0 for c in g['checks'])
assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',(E/'native-02/sail-sdp-replace-using-02-rust.log').read_text())))==[4,9,34,64,123,204]
syntax=read('native-02/sail-sdp-replace-using-02-syntax.json');assert syntax['exit_code']==0 and syntax['sail_commit']==commit and sha(E/'native-02/sail-sdp-replace-using-02-syntax.log')==syntax['log_sha256']
g=read('golden.json');base=g['sail_commit'];delta=read('golden-delta.json')
for c in g['checks']:assert c['exit_code']==0 and sha(E/Path(c['log']).name.removeprefix('sail-sdp-replace-using-'))==c['sha256']
assert set(git('diff','--name-only',base,commit).decode().splitlines())=={d['path']for d in delta}
for d in delta:
 a=json.loads(git('show',base+':'+d['path']));b=json.loads(git('show',commit+':'+d['path']));assert len(a['tests'])==len(b['tests'])==d['cases']
 for x,y in zip(a['tests'],b['tests']):assert {k:v for k,v in x.items()if k!='output'}=={k:v for k,v in y.items()if k!='output'}
 assert [i for i,(x,y)in enumerate(zip(a['tests'],b['tests']))if x!=y]==[c['index']for c in d['changed']]
assert [d['path']for d in delta]==['crates/sail-sql-parser/tests/gold_data/syntax.json']
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
records=[]
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r);assert r['pytest_exit_code']==0 and not r['remaining_listeners'] and r['version']=='4.2.1'
 assert r['test_sha256']==hashlib.sha256(git('show',commit+':python/pysail/tests/spark/pipelines/test_replace_using_registration.py')).hexdigest()
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==8 and all(not list(c)for c in cases)
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256'] and records[1]['runtime_exit_code']==0
assert records[1]['runtime_test_sha256']==hashlib.sha256(git('show',commit+':python/pysail/tests/spark/delta/test_insert_replace_by_name.py')).hexdigest()
runtime=list(ET.parse(E/'sail/runtime.xml').iter('testcase'));assert len(runtime)==2 and all(not list(c)for c in runtime)
c=read('reference-comparison.json');assert len(c)==16 and sum(x['matched']for x in c)==16==s['reference_matches']
for a,b,x in zip(records[0]['cases'],records[1]['cases'],c):assert x['sql']==a['sql']==b['sql'] and x['matched']==all(a.get(k)==b.get(k)for k in ['outcome','error_type','condition','sql_state','parameters'])
assert all(x['matched']for x in c)
assert not s['ordinary_using_execution']
c=read('producer-control.json');assert c['base']==commit and c['exit_code']==101 and sha(E/'producer-control.log')==c['log_sha256'] and '0 passed; 1 failed;'in(E/'producer-control.log').read_text()
assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS REPLACE USING438native+syntax/300+67/paired8/Sail rows2/control;all16 compared vectors,ordinary USING execution unsupported')
