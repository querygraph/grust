from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('native/final-schema-merge-05/candidate.json');commit=c['commit']
f=read('native/final-schema-merge-01/gate.json');assert f['checks'][-1]['exit_code']!=0 and 'unused import'in(E/'native/final-schema-merge-01/clippy.log').read_text()
for label,count in [('final-schema-merge-02',227),('final-schema-merge-03',228),('final-schema-merge-05',228)]:
 g=read('native/'+label+'/gate.json');candidate=read('native/'+label+'/candidate.json');assert g['outcome']=='passed' and g['sail_commit']==candidate['commit']
 for check in g['checks']:assert check['exit_code']==0 and sha(E/'native'/label/(check['name']+'.log'))==check['sha256']
 assert f'{count} passed; 0 failed;'in(E/'native'/label/'rust.log').read_text()
assert read('native/final-schema-merge-05/gate.json')['sail_commit']==commit
for path in c['paths']:assert (E/'source'/path).read_bytes()==subprocess.check_output(['git','-C',S,'show',commit+':'+path])
p=read('public/receipt.json');assert p['outcome']=='passed' and p['sail_commit']==commit and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,errors=0,failures=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
for folder,tests,failures in [('spark-initial',19,10),('spark-second',19,1),('spark-time-discovery',19,1),('spark-public',18,0),('sail-public',18,0),('pre-suffix-sail-public',18,9)]:
 r=read(folder+'/observations.json');assert r['version']=='4.2.1' and not r['remaining_listeners'] and r['pytest_exit_code']==(1 if failures else 0)
 counts={k:0 for k in ['tests','failures','errors','skipped']}
 for suite in ET.parse(E/folder/'pytest.xml').getroot().iter('testsuite'):
  for k in counts:counts[k]+=int(suite.get(k,0))
 assert counts==dict(tests=tests,failures=failures,errors=0,skipped=0),counts
 if folder in ['spark-public','sail-public']:assert r['test_sha256']==sha(E/'source/python/pysail/tests/spark/pipelines/test_virtual_schema_resolution.py')
 if folder=='sail-public':assert r['runtime_commit']==commit and r['cli_sha256']==p['cli_sha256'] and r['server_exit_code']==0
b=read('runtime/observations.json');a=read('spark-runtime/observations.json');old=read('previous-runtime.json');historic=read('historical-spark-runtime.json')
assert b['runtime_commit']==commit and b['cli_sha256']==p['cli_sha256'] and b['probe_completed'] and not b['remaining_listeners'] and b['server_exit_code']==0
assert a['probe_completed'] and a['version']=='4.2.1' and not a['remaining_listeners']
assert len(a['cases'])==len(b['cases'])==len(old['cases'])==12 and old['runtime_commit']==c['base']
summary=final=swapped=0
for x,y,z,h in zip(a['cases'],b['cases'],old['cases'],historic['cases']):
 for key in ['declared','read','missing','sql']:assert x[key]==y[key]==z[key]==h[key]
 for key in ['outcome','error_type','condition','sql_state','parameters','direct','downstream']:assert x[key]==y[key],(key,x,y)
 assert x['message'].replace(a['namespace']+'.','')==y['message'].replace(b['namespace']+'.','')
 if x['direct'] is None:
  final+=1;assert x['condition']=='CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE' and z['condition'] is None
  swapped+=int(x['parameters']!=h['parameters'])
 else:summary+=1
assert (summary,final,swapped)==(9,3,2)
assert 'revision=617618396087429b5627a86ce933bb0f5d6645cb' in (E/'runtime-environment/spark-version-info.properties').read_text()
assert len(read('runtime-environment/jars.json'))==4
for jar in read('runtime-environment/jars.json'):assert sha(Path(jar['path']))==jar['sha256']
pre=read('pre-suffix-runtime/observations.json')
assert len(pre['cases'])==12 and not pre['remaining_listeners']
assert sum(case['direct'] is None and not case['message'].endswith('SQLSTATE: 42825') for case in pre['cases'])==3
for row in read('reference.json'):
 data=subprocess.check_output(['git','-C',row['repository'],'show',row['commit']+':'+row['path']]);assert hashlib.sha256(data).hexdigest()==row['sha256']
print('PASS final schema merge:228native/fmt/Clippy;300+67;paired18public;12fresh runtime diagnostics match;2historical Spark order reversals retained;virtual loader boundary remains required')
