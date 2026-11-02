from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(c,p):return subprocess.check_output(['git','-C',S,'show',c+':'+p])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('sail-sdp-persisted-validation-candidate.json');commit=c['commit'];g=read('sail-sdp-persisted-validation-gate.json')
assert g['outcome']=='passed' and g['sail_commit']==commit
for x in g['checks']:assert x['exit_code']==0 and sha(E/Path(x['log']).name)==x['sha256']
assert '218 passed; 0 failed;'in(E/'sail-sdp-persisted-validation-rust.log').read_text()
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
records=[]
for mode in ['spark','sail','control']:
 r=read(mode+'/observations.json');records.append(r);assert r['version']=='4.2.1' and not r['remaining_listeners']
 for f,h in r['source_sha256'].items():assert hashlib.sha256(blob(commit,f)).hexdigest()==h
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==4
 if mode=='control':assert r['pytest_exit_code']==1 and r['runtime_commit']==c['base'] and all(case.find('failure')is not None for case in cases)
 else:assert r['pytest_exit_code']==0 and all(not list(case)for case in cases)
 if mode=='sail':assert r['runtime_commit']==commit and r['cli_sha256']==p['cli_sha256'] and r['server_exit_code']==0
assert records[0]['source_sha256']==records[1]['source_sha256']==records[2]['source_sha256']
print('PASS persisted-view ordering:218 native/fmt/Clippy/300+67/paired4/unchanged4-failure control; full SDP incomplete')
