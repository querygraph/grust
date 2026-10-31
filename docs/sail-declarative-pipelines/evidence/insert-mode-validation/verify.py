from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET

E=Path(__file__).resolve().parent
S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',S,*args])
for p,h in read('MANIFEST.json').items():assert sha(E/p)==h,p
s=read('summary.json');commit=s['sail_commit'];initial=s['initial_commit']
assert not any(s[k] for k in ['full_conformance','original_scala_suite_executed_on_sail','inventory_changed','streaming_cdc_activated'])
for label,passed in [('01',False),('02',True)]:
 prefix='insert-mode-validation-'+label
 g=read(prefix+'/sail-sdp-'+prefix+'-gate.json')
 assert (g.get('outcome')=='passed')==passed
 assert g['sail_commit']==(commit if passed else initial)
 for c in g['checks']:
  assert sha(E/prefix/Path(c['log']).name)==c['sha256']
  assert c['exit_code']==(101 if not passed and c['name']=='rust' else 0)
 log=(E/prefix/('sail-sdp-'+prefix+'-rust.log')).read_text()
 if passed:assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',log)))==[50,202]
 else:assert '201 passed; 1 failed;' in log and 'proto::plan::tests::test_sql_to_plan' in log
p=read('public/receipt.json')
assert p['outcome']=='passed' and p['sail_commit']==commit
assert p['before']==p['after'] and p['before']['head']==commit and p['before']['detached']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
assert not p['remaining_listener_pids'] and p['server_exit_code']==0
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h,f
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k] for k in ['failures','errors','skipped'])
records=[]
test='python/pysail/tests/spark/pipelines/test_insert_mode_errors.py'
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r)
 assert r['version']=='4.2.1' and r['pytest_exit_code']==0 and not r['remaining_listeners'] and not r['cleanup_errors']
 assert r['test_sha256']==hashlib.sha256(git('show',commit+':'+test)).hexdigest()
 assert r['script_sha256']==sha(E/'insert-mode-feature-probe.py')
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'))
 assert len(cases)==15 and all(not list(t) for t in cases)
 assert len(r['cases'])==6
 for c in r['cases']:
  assert c['error_type']=='ParseException' and c['condition']=='INVALID_STATEMENT_OR_CLAUSE' and c['sql_state']=='42601'
  assert c['parameters']=={'operation':'INSERT INTO ... IF NOT EXISTS'}
  assert not c['contains_filename'] and not c['table_exists']
  assert 'The statement or clause: INSERT INTO ... IF NOT EXISTS is not valid.' in c['message']
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256']
for a,b in zip(*(r['cases']for r in records)):
 for k in ['sql','label','error_type','condition','sql_state','parameters']:assert a[k]==b[k],k
gold='crates/sail-spark-connect/tests/gold_data/plan/ddl_insert_into.json'
assert git('diff','--name-only',initial,commit).decode().strip()==gold
before=json.loads(git('show',initial+':'+gold))['tests'];after=json.loads(git('show',commit+':'+gold))['tests']
assert len(before)==len(after)==32
changed=[]
for i,(a,b) in enumerate(zip(before,after)):
 if a!=b:changed.append(i)
 assert {k:v for k,v in a.items() if k!='output'}=={k:v for k,v in b.items() if k!='output'}
assert changed==[3]
assert 'success' in before[3]['output'] and 'failure' in after[3]['output']
for label in ['rule','file','lower']:
 c=read('control-'+label+'.json');log=E/('control-'+label+'.log')
 assert c['base']==commit and c['exit_code']==101 and sha(log)==c['log_sha256']
 assert '0 passed; 1 failed;' in log.read_text()
 assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS shared INSERT validation:252 native,300+67 public,paired15,three controls;gold32 inputs unchanged/one output corrected;no full-conformance claim')
