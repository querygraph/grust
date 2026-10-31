from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit'];assert not any(s[k]for k in ['full_conformance','inventory_changed','streaming_cdc_activated'])
for label in ['01','02','03','04']:
 prefix='insert-flow-grammar-'+label;g=read('native-'+label+'/sail-sdp-'+prefix+'-gate.json')
 for c in g['checks']:assert sha(E/('native-'+label)/Path(c['log']).name)==c['sha256']
 if label=='04':
  assert g['sail_commit']==commit and g['outcome']=='passed' and all(c['exit_code']==0 for c in g['checks'])
  log=(E/('native-'+label)/('sail-sdp-'+prefix+'-rust.log')).read_text()
  assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',log)))==[4,9,60,123,204]
 else:assert g['checks'][-1]['exit_code']!=0
syntax=read('native-04/sail-sdp-insert-flow-grammar-04-syntax.json');assert syntax['sail_commit']==commit and syntax['exit_code']==0 and sha(E/'native-04/sail-sdp-insert-flow-grammar-04-syntax.log')==syntax['log_sha256']
gold=read('golden-delta.json');assert len(gold)==28 and sum(len(d['changed'])for d in gold)==133
base=read('golden.json')['sail_commit'];assert set(git('diff','--name-only',base,commit).decode().splitlines())=={d['path']for d in gold}
for c in read('golden.json')['checks']:assert c['exit_code']==0 and sha(E/Path(c['log']).name.removeprefix('sail-sdp-insert-flow-'))==c['sha256']
for d in gold:
 a=json.loads(git('show',base+':'+d['path']));b=json.loads(git('show',commit+':'+d['path']))
 assert len(a['tests'])==len(b['tests'])==d['cases']
 changed=[]
 for i,(x,y)in enumerate(zip(a['tests'],b['tests'])):
  assert {k:v for k,v in x.items()if k!='output'}=={k:v for k,v in y.items()if k!='output'}
  if x!=y:changed.append(i);assert set(x['output'])==set(y['output'])=={'failure'}
 assert changed==[c['index']for c in d['changed']]
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h,f
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['failures','errors','skipped'])
records=[]
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r);assert r['pytest_exit_code']==0 and r['version']=='4.2.1' and not r['remaining_listeners']
 assert r['test_sha256']==hashlib.sha256(git('show',commit+':python/pysail/tests/spark/pipelines/test_flow_syntax.py')).hexdigest()
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==24 and all(not list(c)for c in cases)
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256']
comparison=read('reference-comparison.json');assert len(comparison)==16 and sum(c['matched']for c in comparison)==s['reference_matches']
keys=['outcome','error_type','condition','sql_state','parameters']
for a,b,c in zip(records[0]['cases'],records[1]['cases'],comparison):
 assert a['sql']==b['sql']==c['sql'] and a['label']==b['label']==c['label']
 assert c['matched']==all(a.get(k)==b.get(k)for k in keys)
assert [c['label']for c in comparison if not c['matched']]==['ordinary-with','overwrite-partition-ifne','flow-replace-where','flow-replace-using']
for label in ['flow','overwrite','source','hint']:
 c=read('control-'+label+'.json');log=E/('control-'+label+'.log')
 assert c['base']==commit and c['exit_code']==101 and sha(log)==c['log_sha256'] and '0 passed; 1 failed;'in log.read_text()
 assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS INSERT/Flow400native+syntax/300+67/paired24/four controls;133 failure messages only;reference backlog retained')
