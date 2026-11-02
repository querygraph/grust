from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent
S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(commit,path):return subprocess.check_output(['git','-C',S,'show',commit+':'+path])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('sail-sdp-analysis-order-02-candidate.json');commit=c['commit']
g=read('sail-sdp-analysis-order-02-gate.json');assert g['sail_commit']==commit and g['outcome']=='passed'
for x in g['checks']:assert x['exit_code']==0 and sha(E/Path(x['log']).name)==x['sha256']
assert '205 passed; 0 failed;' in (E/'sail-sdp-analysis-order-02-rust.log').read_text()
b=read('sail-sdp-analysis-order-control-v2-candidate.json')
assert b['base']==c['base'] and '0 passed; 1 failed;'in(E/'sail-sdp-analysis-order-control-v2.log').read_text()
assert 'Table or view not found: missing_source'in(E/'sail-sdp-analysis-order-control-v2.log').read_text()
for p in b['paths']:assert blob(commit,p)==blob(b['commit'],p)
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
test='python/pysail/tests/spark/pipelines/test_analysis_order.py'
expected=hashlib.sha256(blob(commit,test)).hexdigest()
for mode in ['spark','sail','control']:
 r=read(mode+'/observations.json');assert r['test_sha256']==expected and r['version']=='4.2.1' and not r['remaining_listeners']
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==(2 if mode=='control' else 10)
 if mode!='control':
  for f,h in r['source_sha256'].items():assert hashlib.sha256(blob(commit,f)).hexdigest()==h
 if mode=='control':
  assert r['runtime_commit']==c['base'] and r['pytest_exit_code']==1 and all(x.find('failure')is not None for x in cases)
 else:assert r['pytest_exit_code']==0 and all(not list(x)for x in cases)
 if mode=='sail':assert r['runtime_commit']==commit and r['cli_sha256']==p['cli_sha256'] and r['server_exit_code']==0
failed=read('initial-public-failure/receipt.json');assert failed['outcome']=='failed' and failed['pytest']==dict(tests=300,failures=4,errors=0,skipped=0)
assert not failed['remaining_listener_pids']
print('PASS analysis order:205 native/300+67/paired10, unchanged-test public and native controls; full SDP remains incomplete')
