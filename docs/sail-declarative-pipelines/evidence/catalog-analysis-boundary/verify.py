from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal';PRIOR=HERE.parent/'wrapped-catalog-identifier'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=load('SHA256.json');assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
c=load('native/candidate.json');final=c['commit'];assert c['base']==git('rev-parse',final+'^')=='4ab0d74bfa8d02c3a9486f4aaa8bf15e174f1091'
assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],final])==(HERE/'native/source.patch').read_bytes()
assert git('diff','--name-only',c['base'],final).splitlines()==['crates/sail-spark-connect/src/pipelines/sql.rs','crates/sail-spark-connect/src/pipelines/sql/tests/preparation.rs']
assert git('rev-parse',c['base']+':crates/sail-plan')==git('rev-parse',final+':crates/sail-plan')
r=load('native/gate.json');assert r['sail_commit']==final and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['178']
r=load('native/control.json');assert r['base']==final and r['exit_code']==101
assert digest(HERE/'native/control.log')==r['log_sha256'] and '0 passed; 1 failed;' in (HERE/'native/control.log').read_text()
assert git('rev-parse',final+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
assert git('diff','--name-only',final,r['control'])=='crates/sail-spark-connect/src/pipelines/sql.rs'
r=load('public/receipt.json');assert r['sail_commit']==final and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(check['exit_code']==0 for check in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,count,probe in [('phases',48,PRIOR/'reference.py'),('arithmetic',14,HERE.parent/'constant-context-lowering/reference.py'),('provenance',20,HERE.parent/'identifier-function-provenance/reference.py')]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==final and receipt['before']['cli_sha256']==r['cli_sha256']
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe)
 assert len(observed['cases'])==count and observed['spark_version']=='4.2.1'
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
 if folder!='phases':assert observed['cases']==json.loads((PRIOR/folder/'probe/observations.json').read_text())['cases'],folder
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
r=load('attempt-01/gate.json');assert r['checks'][-1]['exit_code']==101 and 'StructuredSparkError' in (HERE/'attempt-01/clippy.log').read_text()
for check in r['checks']:assert digest(HERE/'attempt-01'/(check['name']+'.log'))==check['sha256']
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert comparison['before48']['behavior_matched']==25 and comparison['after48']['behavior_matched']==28
print('PASS exact178 Connect, fmt/strictClippy, unchanged0/1 boundary control, fresh300+67/parameter4, phase25→28/48 and previous14+20 unchanged; original full Scala acceptance remains open')
