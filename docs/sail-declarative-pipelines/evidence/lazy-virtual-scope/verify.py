from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent
S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('native/lazy-virtual-scope-03/candidate.json');commit=c['commit']
for label,count in [('lazy-virtual-scope-01',222),('lazy-virtual-scope-02',223),('lazy-virtual-scope-03',223)]:
 g=read('native/'+label+'/gate.json');candidate=read('native/'+label+'/candidate.json')
 assert g['outcome']=='passed' and g['sail_commit']==candidate['commit']
 for check in g['checks']:assert check['exit_code']==0 and sha(E/'native'/label/(check['name']+'.log'))==check['sha256']
 assert f'{count} passed; 0 failed;'in(E/'native'/label/'rust.log').read_text()
for path in c['paths']:
 assert (E/'source'/path).read_bytes()==subprocess.check_output(['git','-C',S,'show',commit+':'+path])
p=read('public/receipt.json');assert p['outcome']=='passed' and p['sail_commit']==commit and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,errors=0,failures=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
for folder,failures in [('spark-initial',9),('spark-public',0),('old-control',9),('sail-public',0)]:
 r=read(folder+'/observations.json');assert r['version']=='4.2.1' and not r['remaining_listeners']
 assert r['pytest_exit_code']==(1 if failures else 0)
 suites=ET.parse(E/folder/'pytest.xml').getroot().iter('testsuite')
 counts={k:0 for k in ['tests','failures','errors','skipped']}
 for suite in suites:
  for k in counts:counts[k]+=int(suite.get(k,0))
 assert counts==dict(tests=9,failures=failures,errors=0,skipped=0),counts
 if folder!='spark-initial':assert r['test_sha256']==sha(E/'source/python/pysail/tests/spark/pipelines/test_virtual_schema_resolution.py')
 if folder=='sail-public':assert r['runtime_commit']==commit and r['cli_sha256']==p['cli_sha256'] and r['server_exit_code']==0
 if folder=='old-control':assert r['runtime_commit']==c['base'] and r['server_exit_code']==0
b=read('runtime/observations.json');a=read('spark-runtime.json');old=read('previous-runtime.json')
assert b['runtime_commit']==commit and b['cli_sha256']==p['cli_sha256'] and b['probe_completed'] and not b['remaining_listeners'] and b['server_exit_code']==0
assert len(a['cases'])==len(b['cases'])==len(old['cases'])==12
assert old['runtime_commit']==c['base']
summary=final=0
for x,y,z in zip(a['cases'],b['cases'],old['cases']):
 for key in ['declared','read','missing','sql']:assert x[key]==y[key]==z[key]
 if x['direct'] is not None:
  summary+=1
  for field in ['outcome','error_type','condition','sql_state','parameters','direct','downstream']:assert x[field]==y[field],(field,x,y)
  assert x['message'].replace(a['namespace']+'.','')==y['message'].replace(b['namespace']+'.','')
 else:
  final+=1
  assert x['condition']=='CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE'
  for field in ['outcome','error_type','condition','sql_state','parameters','direct','downstream','message']:assert y[field]==z[field]
assert (summary,final)==(9,3)
print('PASS lazy virtual scope:223native/fmt/Clippy,300+67,paired9public; oldcontrol9fails;9/12summary diagnostics match Spark,3final merge-codec gaps retained')
