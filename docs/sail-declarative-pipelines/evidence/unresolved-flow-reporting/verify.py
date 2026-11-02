from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(c,p):return subprocess.check_output(['git','-C',S,'show',c+':'+p])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('native-05/sail-sdp-unresolved-flows-05-candidate.json');commit=c['commit'];g=read('native-05/sail-sdp-unresolved-flows-05-gate.json')
assert g['sail_commit']==commit and g['outcome']=='passed'
for x in g['checks']:assert x['exit_code']==0 and sha(E/'native-05'/Path(x['log']).name)==x['sha256']
assert '217 passed; 0 failed;'in(E/'native-05/sail-sdp-unresolved-flows-05-rust.log').read_text()
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
records=[]
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r)
 assert r['pytest_exit_code']==0 and r['version']=='4.2.1' and not r['remaining_listeners']
 for f,h in r['source_sha256'].items():assert hashlib.sha256(blob(commit,f)).hexdigest()==h
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==13 and all(not[x for x in case if x.tag in ['failure','error','skipped']]for case in cases)
assert records[0]['pytest_nodes']==records[1]['pytest_nodes'] and records[0]['source_sha256']==records[1]['source_sha256']
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256'] and records[1]['server_exit_code']==0
r=read('control/observations.json');assert r['runtime_commit']==c['base'] and r['pytest_exit_code']==1 and not r['remaining_listeners']
assert r['test_sha256']==hashlib.sha256(blob(commit,'python/pysail/tests/spark/pipelines/test_resolution_failures.py')).hexdigest()
cases=list(ET.parse(E/'control/pytest.xml').iter('testcase'));assert len(cases)==12 and all(case.find('failure')is not None for case in cases)
f=read('public-initial-failure/receipt.json');assert f['outcome']=='failed' and f['pytest']==dict(tests=300,failures=1,errors=0,skipped=0) and not f['remaining_listener_pids']
assert read('native-01/sail-sdp-unresolved-flows-01-gate.json')['checks'][-1]['exit_code']!=0
print('PASS O2:217 native/fmt/strictClippy/300+67/paired13/unchanged-primary12 control; full SDP remains incomplete')
