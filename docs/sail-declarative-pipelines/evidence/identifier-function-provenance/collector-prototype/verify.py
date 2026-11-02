from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;SAIL='/Users/alexy/src/sail-pipelines-proposal'
def load(name):return json.loads((HERE/name).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
manifest=load('SHA256.json');assert set(manifest)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in manifest.items():assert digest(HERE/path)==sha,path
candidate=load('native/candidate.json');FINAL=candidate['commit'];assert candidate['base']==git('rev-parse',FINAL+'^')=='15fd1888c3a474a361afe46d235d52051738229c'
r=load('native/gate.json');assert r['sail_commit']==FINAL and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['100','177']
assert subprocess.check_output(['git','-C',SAIL,'diff',candidate['base'],FINAL])==(HERE/'native/source.patch').read_bytes()
for label,passed,failed in [('builder',1,2),('typeof',1,2),('udf',2,1),('parent',1,2)]:
 c=load('native/'+label+'-control.json');assert c['base']==FINAL and c['exit_code']==101 and digest(HERE/'native'/(label+'-control.log'))==c['log_sha256']
 assert f'{passed} passed; {failed} failed;' in (HERE/'native'/(label+'-control.log')).read_text()
 test='crates/sail-plan/src/resolver/identifier/provenance_tests.rs';assert git('rev-parse',FINAL+':'+test)==git('rev-parse',c['control']+':'+test)==c['test_blob']
assert [c['exit_code'] for c in load('attempt-01/gate.json')['checks']]==[0,101] and 'collapsible_if' in (HERE/'attempt-01/clippy.log').read_text()
failed=load('baseline-setup-failure/receipt.json');assert failed['exit_code']==1 and failed['expected_commit']==candidate['base'] and failed['observed_commit']==load('attempt-01/candidate.json')['commit']
for folder,probe,count in [('spark','reference.py',20),('initial16/spark','initial16/reference.py',16),('initial18/spark','initial18/reference.py',18)]:
 r=load(folder+'/observations.json');assert r['spark_version']=='4.2.1' and len(r['cases'])==count and r['harness_sha256']==digest(HERE/probe)
 assert r['listener_after_stop']=={'exit_code':1,'stdout':''}
r=load('public/receipt.json');assert r['sail_commit']==FINAL and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0} and r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(c['exit_code']==0 for c in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,probe,count,commit in [('baseline','reference.py',20,candidate['base']),('candidate','reference.py',20,FINAL),('validation','validation-probes/reference.py',34,FINAL),('replacement','validation-probes/runtime-replacement-reference.py',7,FINAL)]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==commit
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(HERE/probe) and len(observed['cases'])==count
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 if folder!='baseline':assert receipt['before']['cli_sha256']==r['cli_sha256']
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
primary=load('candidate/receipt.json');assert primary['parameter_tests']['exit_code']==0
assert primary['before']['parameter_tests_sha256']==hashlib.sha256(subprocess.check_output(['git','-C',SAIL,'show',FINAL+':python/pysail/tests/spark/dataframe/test_identifier_clause.py'])).hexdigest()
suite=ET.parse(HERE/'candidate/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
def conditions(case):return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('run_error','')+'\n'+'\n'.join(c['message'] for c in case.get('events',[]) if isinstance(c,dict)))))
for kind,count,probe in [('dynamic',13,'reference.py'),('namespace',3,'namespace-reference.py'),('expression',2,'expression-reference.py')]:
 spark=json.loads((HERE.parent/'computed-identifier-binding'/('spark-'+kind)/'observations.json').read_text());sail=load(kind+'/probe/observations.json');receipt=load(kind+'/receipt.json')
 assert len(spark['cases'])==len(sail['cases'])==count and receipt['before']==receipt['after'] and receipt['before']['sail_commit']==FINAL
 assert receipt['before']['probe_sha256']==spark['harness_sha256']==sail['harness_sha256']==digest(HERE/'binding-probes'/probe)
 assert receipt['before']['cli_sha256']==r['cli_sha256'] and receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for file in receipt['files']:assert digest(HERE/kind/file['path'])==file['sha256']
 for expected,actual in zip(spark['cases'],sail['cases']):
  for key in (['name','query','returned','rows','session_namespace'] if kind=='namespace' else ['name','definitions','query','consumer_conf','run_returned','result_exists','rows']):assert expected.get(key)==actual.get(key),(kind,key,actual['name'])
  if kind!='namespace':assert conditions(expected)==conditions(actual)
reference=load('reference-source.json')
for file in reference['files']:assert hashlib.sha256(subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',reference['spark_commit']+':'+file['path']])).hexdigest()==file['sha256']
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert (comparison['baseline20']['behavior_matched'],comparison['candidate20']['behavior_matched'],comparison['candidate20']['metadata_matched'])==(11,19,11)
assert comparison['validation34']['behavior_matched']==29 and comparison['replacement7']['behavior_matched']==6
print('PASS exact100+177, four unchanged controls, fresh300+67, parameter4, provenance19/20, validation29/34, binding13+3+2; full metadata/function PATH/SDP goal remain open')
