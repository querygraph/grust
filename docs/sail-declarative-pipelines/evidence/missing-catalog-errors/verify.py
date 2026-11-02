from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal';PRIOR=HERE.parent/'catalog-analysis-boundary'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=load('SHA256.json');assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
c=load('native/candidate.json');final=c['commit'];assert c['base']==git('rev-parse',final+'^')=='4761d0064b592f66647dec807801c57fcfc546c9'
assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],final])==(HERE/'native/source.patch').read_bytes()
assert git('rev-parse',c['base']+':crates/sail-plan')==git('rev-parse',final+':crates/sail-plan')
assert git('rev-parse',c['base']+':crates/sail-catalog')==git('rev-parse',final+':crates/sail-catalog')
physical=git('show',final+':crates/sail-physical-plan/src/catalog_command.rs')
assert 'if is_set_current_catalog =>' in physical and 'CatalogError::CommitStateUnknown(_) => DataFusionError::External(Box::new(e))' in physical
r=load('native/gate.json');assert r['sail_commit']==final and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['140','15','104','180']
for kind in ['diagnostic','hierarchy']:
 r=load('native/'+kind+'-control.json');assert r['base']==final and r['exit_code']==101
 assert digest(HERE/'native'/(kind+'-control.log'))==r['log_sha256'] and '0 passed; 1 failed;' in (HERE/'native'/(kind+'-control.log')).read_text()
 assert git('rev-parse',final+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
r=load('public/receipt.json');assert r['sail_commit']==final and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(check['exit_code']==0 for check in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
spark=load('spark/observations.json');assert spark['spark_version']=='4.2.1' and len(spark['cases'])==16 and spark['harness_sha256']==digest(HERE/'reference.py') and spark['listener_after_stop']=={'exit_code':1,'stdout':''}
assert spark['spark_source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
source=load('spark-source.json');assert source['commit']==spark['spark_source_commit']
for path,sha in source['files'].items():assert hashlib.sha256(subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',source['commit']+':'+path])).hexdigest()==sha
old_public=json.loads((PRIOR/'public/receipt.json').read_text())
for folder,count,probe,commit,cli in [('baseline',16,HERE/'reference.py',c['base'],old_public['cli_sha256']),('candidate',16,HERE/'reference.py',final,r['cli_sha256']),('phases',48,HERE.parent/'wrapped-catalog-identifier/reference.py',final,r['cli_sha256']),('arithmetic',14,HERE.parent/'constant-context-lowering/reference.py',final,r['cli_sha256']),('provenance',20,HERE.parent/'identifier-function-provenance/reference.py',final,r['cli_sha256'])]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==commit and receipt['before']['cli_sha256']==cli
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe)
 assert len(observed['cases'])==count and observed['spark_version']=='4.2.1'
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
assert load('provenance/probe/observations.json')['cases']==json.loads((PRIOR/'provenance/probe/observations.json').read_text())['cases']
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
# Preserve the failed compile and the reviewed broader mapping, never advanced.
a=load('attempt-01/gate.json');assert a['checks'][-1]['exit_code']==101 and 'error_info' in (HERE/'attempt-01/clippy.log').read_text()
for check in a['checks']:assert digest(HERE/'attempt-01'/(check['name']+'.log'))==check['sha256']
a=load('attempt-02/gate.json');assert a['outcome']=='passed' and a['sail_commit']!=final
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'attempt-02/rust.log').read_text())==['140','15','104','180']
for check in a['checks']:assert digest(HERE/'attempt-02'/(check['name']+'.log'))==check['sha256']
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert comparison['candidate16']['behavior_matched']==comparison['candidate16']['metadata_matched']==12
assert comparison['candidate16']['wire_matched']==10 and comparison['baseline16']['behavior_matched']==0
assert comparison['before48']['behavior_matched']==28 and comparison['after48']['behavior_matched']>28
baseline={c['name']:c for c in load('baseline/probe/observations.json')['cases']};candidate={c['name']:c for c in load('candidate/probe/observations.json')['cases']}
for name in ['sql_USE missing_catalog.db','sql_SELECT * FROM missing_catalog.db.input','sql_SHOW TABLES IN missing_catalog.db']:
 for key in ['returned','rows','exception_type','condition','sql_state','parameters','error']:assert baseline[name].get(key)==candidate[name].get(key),(name,key)
print('PASS exact439 Rust/fmt/strictClippy, unchanged diagnostic/hierarchy0/1 controls, fresh300+67/parameter4; missing12/16 metadata,10 exact native hierarchies; namespace errors unchanged; full original Scala acceptance remains open')
