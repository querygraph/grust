from pathlib import Path
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
P=Path(__file__).resolve().parent;R='/Users/alexy/src/sail-pipelines-proposal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads((P/p).read_text())
def git(*a):return subprocess.check_output(['git','-C',R,*a])
m=load('SHA256.json');assert {f['path'] for f in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in m['files']:assert sha(P/f['path'])==f['sha256']
c=load('candidate.json');assert c['commit']=='63f5bd3b3f0f8bd9b23607161d5988df853a738c' and c['base']=='4070e895b69338eb19f22643f0e40815da89ff34'
assert git('diff',c['base'],c['commit'])==(P/'source.patch').read_bytes()
assert set(git('diff','--name-only',c['base'],c['commit']).decode().splitlines())==set(c['paths']) and len(c['paths'])==3
r=load('gate.json');assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for x in r['checks']:assert x['exit_code']==0 and sha(P/(x['name']+'.log'))==x['sha256']
assert '117 passed; 0 failed;' in (P/'rust.log').read_text()
r=load('control.json');assert r['base']==c['commit'] and r['exit_code']==101 and sha(P/'control.log')==r['log_sha256']
assert git('diff',r['base'],r['control'])==(P/'control.patch').read_bytes()
assert git('diff','--name-only',r['base'],r['control']).decode().strip()==r['path']
assert git('rev-parse',r['base']+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])
assert '0 passed; 3 failed;' in (P/'control.log').read_text()
for n in ['01','02']:
 d='attempt-'+n+'/';a=load(d+'candidate.json');g=load(d+'gate.json')
 assert git('diff',a['base'],a['commit'])==(P/(d+'source.patch')).read_bytes()
 for x in g['checks']:assert sha(P/(d+x['name']+'.log'))==x['sha256']
 assert g['checks'][-1]['exit_code']!=0
assert '116 passed; 1 failed;' in (P/'attempt-02/rust.log').read_text() and 'unknown field: value' in (P/'attempt-02/rust.log').read_text()
p=load('public-regression/receipt.json');assert p['outcome']=='passed' and p['sail_commit']==c['commit'] and not p['remaining_listener_pids']
for file,digest in p['artifact_sha256'].items():assert sha(P/'public-regression'/file)==digest
x=ET.parse(P/'public-regression/pytest.xml').getroot().find('testsuite');assert x is not None and (x.get('tests'),x.get('failures'),x.get('errors'),x.get('skipped'))==('300','0','0','0')
u=load('public-regression/upstream.json');assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0
s=load('spark/observations.json');v=load('public/observations.json')
assert len(s['cases'])==len(v['cases'])==136 and s['spark_version']==v['spark_version']=='4.2.1'
assert s['spark_commit']=='617618396087429b5627a86ce933bb0f5d6645cb' and not s['remaining_listener_pids'] and not v['remaining_listener_pids']
assert v['sail_commit']==c['commit'] and v['cli_sha256']==p['cli_sha256']
assert s['script_sha256']==sha(P/'spark-oracle.py') and v['script_sha256']==sha(P/'public-probe.py')
assert v['spark_oracle_sha256']==sha(P/'spark/observations.json')
for record in s['cases']+v['cases']:assert record['effective_ansi']==str(record['ansi']).lower()
for record in v['cases']:
 if record['source'] in [None,'bad','','1.5','NaN','nan','Inf','-Infinity','1e1000','1e-1000','+Infinity','1_0','null']:assert record['behavior_match'],record
assert sum(x['behavior_match'] for x in v['cases'])==120
assert sum(x.get('schema_match') is True for x in v['cases'])==104
assert sum(x.get('schema_match') is False for x in v['cases'])==20
assert all(x['ansi'] and not x['is_try'] for x in v['cases'] if x.get('schema_match') is False)
failed=load('public-attempt-01/observations.json');assert not failed['cases'] and not failed['remaining_listener_pids']
check=subprocess.run([sys.executable,str(P/'check-conformance.py')],capture_output=True,text=True)
assert check.returncode==1 and check.stdout==(P/'conformance-failure.log').read_text()
peer=load('peer-review.json');text=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',peer['commit']+':'+peer['path']],text=True)
assert text[text.index(peer['section']):]==(P/'peer-review.md').read_text() and sha(P/'peer-review.md')==peer['extract_sha256']
print('PASS legacy floating cast source/native117/control0-of3/public300+67/RPC136 evidence; wider syntax mismatches retained')
