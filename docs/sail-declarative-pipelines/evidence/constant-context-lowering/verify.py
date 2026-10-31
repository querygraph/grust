from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;SAIL='/Users/alexy/src/sail-pipelines-proposal';PRIOR=HERE.parent/'identifier-function-provenance'
def load(name):return json.loads((HERE/name).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
manifest=load('SHA256.json');assert set(manifest)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in manifest.items():assert digest(HERE/path)==sha,path
candidate=load('native/candidate.json');FINAL=candidate['commit'];assert candidate['base']==git('rev-parse',FINAL+'^')=='25534e8eaf8aecc7e769309acae357aab14fd127'
r=load('native/gate.json');assert r['sail_commit']==FINAL and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['101','177']
assert subprocess.check_output(['git','-C',SAIL,'diff',candidate['base'],FINAL])==(HERE/'native/source.patch').read_bytes()
c=load('native/control.json');assert c['base']==FINAL and c['exit_code']==101 and digest(HERE/'native/control.log')==c['log_sha256'] and '0 passed; 1 failed;' in (HERE/'native/control.log').read_text()
test='crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs';assert git('rev-parse',FINAL+':'+test)==git('rev-parse',c['control']+':'+test)==c['test_blob']
r=load('spark/observations.json');assert r['spark_version']=='4.2.1' and len(r['cases'])==14 and r['harness_sha256']==digest(HERE/'reference.py') and r['listener_after_stop']=={'exit_code':1,'stdout':''}
r=load('public/receipt.json');assert r['sail_commit']==FINAL and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0} and r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(c['exit_code']==0 for c in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,probe,count,commit in [('baseline',HERE/'reference.py',14,candidate['base']),('candidate',HERE/'reference.py',14,FINAL),('provenance',PRIOR/'reference.py',20,FINAL),('validation',PRIOR/'validation-probes/reference.py',34,FINAL),('replacement',PRIOR/'validation-probes/runtime-replacement-reference.py',7,FINAL)]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json');assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==commit
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe) and len(observed['cases'])==count
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 if folder!='baseline':assert receipt['before']['cli_sha256']==r['cli_sha256']
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
def conditions(case):return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',case.get('run_error','')+'\n'+'\n'.join(c['message'] for c in case.get('events',[]) if isinstance(c,dict)))))
for kind,count,probe in [('dynamic',13,'reference.py'),('namespace',3,'namespace-reference.py'),('expression',2,'expression-reference.py')]:
 spark=json.loads((HERE.parent/'computed-identifier-binding'/('spark-'+kind)/'observations.json').read_text());sail=load(kind+'/probe/observations.json');receipt=load(kind+'/receipt.json')
 assert len(spark['cases'])==len(sail['cases'])==count and receipt['before']==receipt['after'] and receipt['before']['sail_commit']==FINAL
 assert receipt['before']['probe_sha256']==spark['harness_sha256']==sail['harness_sha256']==digest(PRIOR/'binding-probes'/probe)
 assert receipt['before']['cli_sha256']==r['cli_sha256'] and receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for file in receipt['files']:assert digest(HERE/kind/file['path'])==file['sha256']
 for expected,actual in zip(spark['cases'],sail['cases']):
  for key in (['name','query','returned','rows','session_namespace'] if kind=='namespace' else ['name','definitions','query','consumer_conf','run_returned','result_exists','rows']):assert expected.get(key)==actual.get(key),(kind,key,actual['name'])
  if kind!='namespace':assert conditions(expected)==conditions(actual)
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert comparison['baseline14']['behavior_matched']==2 and comparison['candidate14']['behavior_matched']==6
print('PASS exact101+177, unchanged0/1 arithmetic control, public300+67, parameter4, arithmetic6/14 with four corrected cases, previous19/20 and29/34; full goal open')
