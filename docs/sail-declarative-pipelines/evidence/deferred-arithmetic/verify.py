from pathlib import Path
import hashlib,json,re,subprocess,sys,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal';PRIOR=HERE.parent/'missing-catalog-errors'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=load('SHA256.json');assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
c=load('native/candidate.json');final=c['commit'];assert c['base']==git('rev-parse',final+'^')=='55c237c489d551bb82b1aa9da3d6b035ab4a57ca'
assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],final])==(HERE/'native/source.patch').read_bytes()
r=load('native/gate.json');assert r['sail_commit']==final and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['229','394','106','180']
for kind,passed,failed in [('eager',1,2),('codec',0,1)]:
 r=load('native/'+kind+'-control.json');assert r['base']==final and r['exit_code']==101
 assert digest(HERE/'native'/(kind+'-control.log'))==r['log_sha256'] and f'{passed} passed; {failed} failed;' in (HERE/'native'/(kind+'-control.log')).read_text()
 assert git('rev-parse',final+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
r=load('public/receipt.json');assert r['sail_commit']==final and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(check['exit_code']==0 for check in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,probe,count in [('spark','reference.py',40),('spark-schema','schema-reference.py',40),('runtime-spark','runtime-gap-reference.py',12)]:
 observed=load(folder+'/observations.json');assert observed['spark_version']=='4.2.1' and len(observed['cases'])==count and observed['harness_sha256']==digest(HERE/probe)
 assert observed['listener_after_stop']=={'exit_code':1,'stdout':''} and observed['spark_source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
source=load('spark-source.json')
for path,sha in source['files'].items():assert hashlib.sha256(subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',source['commit']+':'+path])).hexdigest()==sha
old_public=json.loads((PRIOR/'public/receipt.json').read_text())
for folder,count,probe,commit,cli in [('baseline',40,HERE/'reference.py',c['base'],old_public['cli_sha256']),('baseline-schema',40,HERE/'schema-reference.py',c['base'],old_public['cli_sha256']),('baseline-runtime',12,HERE/'runtime-gap-reference.py',c['base'],old_public['cli_sha256']),('candidate-schema',40,HERE/'schema-reference.py',final,r['cli_sha256']),('candidate-runtime',12,HERE/'runtime-gap-reference.py',final,r['cli_sha256']),('phases',48,HERE.parent/'wrapped-catalog-identifier/reference.py',final,r['cli_sha256']),('arithmetic',14,HERE.parent/'constant-context-lowering/reference.py',final,r['cli_sha256']),('provenance',20,HERE.parent/'identifier-function-provenance/reference.py',final,r['cli_sha256'])]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==commit and receipt['before']['cli_sha256']==cli
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe)
 assert len(observed['cases'])==count and observed['spark_version']=='4.2.1'
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
assert load('provenance/probe/observations.json')['cases']==json.loads((PRIOR/'provenance/probe/observations.json').read_text())['cases']
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite');assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
# Both initial fixture failures and the real signed-zero regression stay visible.
a=load('attempt-01/gate.json');assert a['checks'][-1]['exit_code']==101 and 'unresolved import' in (HERE/'attempt-01/clippy.log').read_text()
a=load('attempt-02/gate.json');assert a['checks'][-1]['exit_code']==101 and 'bytes.is_empty()' in (HERE/'attempt-02/rust.log').read_text()
a=load('attempt-03/gate.json');assert a['outcome']=='passed' and a['sail_commit']!=final
old=load('attempt-03/public/receipt.json');assert old['sail_commit']==a['sail_commit'] and old['outcome']=='failed' and old['pytest']=={'tests':300,'failures':2,'errors':0,'skipped':0}
assert old['server_exit_code']==0 and old['remaining_listener_pids']==[]
for path,sha in old['artifact_sha256'].items():assert digest(HERE/'attempt-03/public'/path)==sha
assert set(re.findall(r'^FAILED (.+)',(HERE/'attempt-03/public/pytest.log').read_text(),re.M))=={'python/pysail/tests/spark/dataframe/test_math.py::test_signed_zero_divisors[-0.0-float]','python/pysail/tests/spark/dataframe/test_math.py::test_signed_zero_divisors[-0.0-double]'}
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert (comparison['before40']['behavior_matched'],comparison['after40']['behavior_matched'],comparison['after40']['metadata_matched'],comparison['after40']['wire_matched'],comparison['after40']['schema_matched'])==(17,40,40,40,33)
assert comparison['after48']['behavior_matched']==33 and comparison['after14']['behavior_matched']==10
# This conformance check MUST still fail; these semantics remain required work.
result=subprocess.run([sys.executable,str(HERE/'runtime-gap-check.py')],capture_output=True,text=True)
gap=load('runtime-gap-result.json');assert result.returncode==gap['exit_code']==1 and json.loads(result.stdout)==gap['result']
assert gap['result']['passed']==gap['result']['failed']==6
assert set(gap['result']['failures'])=={'ansi_null_input_div','ansi_null_input_divide','ansi_null_input_mod','ansi_volatile_null_divide','ansi_window_null_divide','ansi_pmod_zero'}
assert digest(HERE/'runtime-gap-check.log')==gap['log_sha256']
probe=load('volatile-divisor-receipt.json');assert probe['base']==final and probe['exit_code']==101
assert digest(HERE/'volatile-divisor.log')==probe['log_sha256'] and digest(HERE/'volatile-divisor-regression.rs')==probe['snippet_sha256']
assert '0 passed; 1 failed;' in (HERE/'volatile-divisor.log').read_text() and 'a divisor must be evaluated once' in (HERE/'volatile-divisor.log').read_text()
assert re.search(r'left: 6\s+right: 1', (HERE/'volatile-divisor.log').read_text())
assert subprocess.check_output(['git','-C',SAIL,'show',probe['probe']+':'+probe['test_path']])==subprocess.check_output(['git','-C',SAIL,'show',final+':'+probe['test_path']])+(HERE/'volatile-divisor-regression.rs').read_bytes()
assert git('diff','--name-only',final,probe['probe'])==probe['test_path']
domain=load('input-domain-result.json');check=subprocess.run([sys.executable,str(HERE/'input-domain-check.py')],capture_output=True,text=True)
assert check.returncode==domain['exit_code']==1 and json.loads(check.stdout)==domain['result']
assert domain['result']['passed']==0 and domain['result']['failed']==2
assert digest(HERE/'input-domain-check.log')==domain['log_sha256']
observed=load('domain-spark/observations.json');receipt=load('domain-sail/receipt.json')
assert len(observed['cases'])==2 and observed['spark_version']=='4.2.1' and observed['harness_sha256']==digest(HERE/'input-domain-reference.py') and observed['listener_after_stop']=={'exit_code':1,'stdout':''}
assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==final and receipt['before']['cli_sha256']==load('public/receipt.json')['cli_sha256']
assert receipt['before']['probe_sha256']==digest(HERE/'input-domain-reference.py') and receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
for file in receipt['files']:assert digest(HERE/'domain-sail'/file['path'])==file['sha256']
test=load('test-domain/candidate.json');assert test['base']==final
assert git('diff','--name-only',final,test['commit'])=='crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs'
path='crates/sail-plan/src/resolver/identifier/arithmetic_tests.rs'
old=subprocess.check_output(['git','-C',SAIL,'show',final+':'+path]);new=subprocess.check_output(['git','-C',SAIL,'show',test['commit']+':'+path])
assert old.replace(b'                    ("DIV", ScalarValue::Int64(None)),\n',b'')==new
assert '#[cfg(test)]\n#[path = "identifier/arithmetic_tests.rs"]\nmod arithmetic_tests;' in git('show',final+':crates/sail-plan/src/resolver/identifier.rs')
r=load('test-domain/gate.json');assert r['sail_commit']==test['commit'] and r['outcome']=='passed' and r['packages']==['sail-plan']
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'test-domain'/(check['name']+'.log'))==check['sha256']
assert 'test result: ok. 106 passed; 0 failed;' in (HERE/'test-domain/rust.log').read_text()
print('PASS exact909 Rust/fmt/strictClippy, unchanged eager1/2+codec0/1 controls, fresh300+67/parameter4; core40/40 with33 exact schemas; six runtime conformance failures remain required, full original Scala acceptance open')
