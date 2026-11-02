from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal'
PRIOR=HERE.parent/'constant-name-policy'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=load('SHA256.json');assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
c=load('native/candidate.json');final=c['commit'];assert c['base']==git('rev-parse',final+'^')=='f0a232af259fa2bf33c089d5439ffb45fa78061e'
assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],final])==(HERE/'native/source.patch').read_bytes()
r=load('native/gate.json');assert r['sail_commit']==final and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['104','177']
for kind,failed in [('control',3),('precedence-control',1)]:
 r=load('native/'+kind+'.json');assert r['base']==final and r['exit_code']==101
 assert digest(HERE/'native'/(kind+'.log'))==r['log_sha256'] and f'0 passed; {failed} failed;' in (HERE/'native'/(kind+'.log')).read_text()
 assert git('rev-parse',final+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
 assert git('diff','--name-only',final,r['control'])=='crates/sail-plan/src/resolver/constant.rs'
def public(folder,commit):
 r=load(folder+'/receipt.json');assert r['sail_commit']==commit and r['outcome']=='passed' and r['before']==r['after']
 assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
 assert r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
 assert all(check['exit_code']==0 for check in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
 for path,sha in r['artifact_sha256'].items():assert digest(HERE/folder/path)==sha
 return r
qualified=public('public',final)
spark=load('spark/observations.json');assert spark['spark_version']=='4.2.1' and len(spark['cases'])==48 and spark['harness_sha256']==digest(HERE/'reference.py') and spark['listener_after_stop']=={'exit_code':1,'stdout':''}
for folder,count,probe in [('phases',48,HERE/'reference.py'),('arithmetic',14,HERE.parent/'constant-context-lowering/reference.py'),('provenance',20,HERE.parent/'identifier-function-provenance/reference.py')]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==final and receipt['before']['cli_sha256']==qualified['cli_sha256']
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe)
 assert len(observed['cases'])==count and observed['spark_version']=='4.2.1'
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
 if folder!='phases':
  old='arithmetic' if folder=='arithmetic' else 'provenance'
  assert observed['cases']==json.loads((PRIOR/old/'probe/observations.json').read_text())['cases'],folder
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
# Preserve the compile failure and the reviewed, unadvanced table-route candidate.
r=load('attempt-01/gate.json');assert r['checks'][-1]['exit_code']==101 and 'mismatched types' in (HERE/'attempt-01/clippy.log').read_text()
for check in r['checks']:assert digest(HERE/'attempt-01'/(check['name']+'.log'))==check['sha256']
old=load('attempt-02/candidate.json')['commit'];assert old!=final and load('attempt-02/gate.json')['sail_commit']==old
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'attempt-02/rust.log').read_text())==['103','177']
old_public=public('attempt-02/public',old);r=load('attempt-02/catalog48/receipt.json')
assert r['before']==r['after'] and r['before']['sail_commit']==old and r['before']['cli_sha256']==old_public['cli_sha256'] and r['before']['probe_sha256']==digest(HERE/'reference.py')
assert r['server_exit_code']==r['probe_exit_code']==0 and r['remaining_listener_pids']==[]
for f in r['files']:assert digest(HERE/'attempt-02/catalog48'/f['path'])==f['sha256']
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert comparison['original32']['behavior_matched']==13
assert comparison['candidate32']['behavior_matched']>13 and comparison['candidate48']['behavior_matched']>comparison['reviewed48']['behavior_matched']
print('PASS exact104+177, unchanged0/3+0/1 controls, strictClippy/fmt, fresh300+67, parameter4, phase48 improvements and previous14+20 unchanged; full original Scala acceptance remains open')
