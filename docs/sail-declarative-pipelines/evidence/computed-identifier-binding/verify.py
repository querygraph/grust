from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent;SAIL='/Users/alexy/src/sail-pipelines-proposal'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
def load(name):return json.loads((HERE/name).read_text())
manifest=load('SHA256.json');assert set(manifest)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in manifest.items():assert digest(HERE/path)==sha,path
reference=load('reference-source.json')
for file in reference['files']:assert hashlib.sha256(subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',reference['spark_commit']+':'+file['path']])).hexdigest()==file['sha256']
native=load('native/candidate.json')['commit'];final=load('sdp/candidate.json')['commit']
assert git('rev-parse',final+'^')==native and git('rev-parse',native+'^')=='ccb6fb21240b1b4d2962da833a74a17ade5e84c3'
for folder,counts in [('native',[94,176]),('sdp',[94,177])]:
 c=load(folder+'/candidate.json');r=load(folder+'/gate.json');assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
 for check in r['checks']:assert check['exit_code']==0 and digest(HERE/folder/(check['name']+'.log'))==check['sha256']
 assert list(map(int,re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/folder/'rust.log').read_text())))==counts
 assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],c['commit']])==(HERE/folder/'source.patch').read_bytes()
for label in ['lookup','namespace']:
 c=load('native/'+label+'-control.json');assert c['base']==native and c['exit_code']==101
 log=HERE/'native'/(label+'-control.log');assert digest(log)==c['log_sha256'] and '1 passed; 1 failed;' in log.read_text()
 test='crates/sail-plan/src/resolver/query/late_bound_scope_tests.rs'
 assert git('rev-parse',native+':'+test)==git('rev-parse',c['control']+':'+test)==c['test_blob']
c=load('sdp/target-control.json');assert c['base']==final and c['exit_code']==101
assert digest(HERE/'sdp/target-control.log')==c['log_sha256'] and '0 passed; 1 failed;' in (HERE/'sdp/target-control.log').read_text()
test='crates/sail-spark-connect/src/pipelines/config/runtime_tests.rs';assert git('rev-parse',final+':'+test)==git('rev-parse',c['control']+':'+test)==c['test_blob']
failed=load('sdp-fixture-failure/gate.json');assert [c['exit_code'] for c in failed['checks']]==[0,0,101]
assert '176 passed; 1 failed;' in (HERE/'sdp-fixture-failure/rust.log').read_text() and 'session extension not found: DataSourceRegistry' in (HERE/'sdp-fixture-failure/rust.log').read_text()
assert '0 passed; 0 failed;' in (HERE/'control-filter-failure/late-bound-lookup-control.log').read_text()
assert '2 passed; 0 failed;' in (HERE/'namespace-control-vacuous/late-bound-namespace-control.log').read_text()
for folder,probe,count in [('spark-dynamic','reference.py',13),('spark-expression','expression-reference.py',2),('spark-namespace','namespace-reference.py',3),('spark-namespace-initial','namespace-initial-reference.py',3),('spark-frozen-files','frozen-files-reference.py',3)]:
 r=load(folder+'/observations.json');assert r['spark_version']=='4.2.1' and len(r['cases'])==count and r['harness_sha256']==digest(HERE/probe)
r=load('spark-namespace/observations.json');assert [c['rows'] for c in r['cases']]==[[{'foo':9}],[{'foo':9}],[{'foo':10}]] and all(c['session_namespace']=='binding_b' for c in r['cases'])
r=load('spark-expression/observations.json');assert all('NOT_A_CONSTANT_STRING.NOT_CONSTANT' in c['events'][0]['message'] for c in r['cases'])
r=load('spark-frozen-files/observations.json');assert r['listener_after_stop']=={'exit_code':1,'stdout':''}
cases={c['name']:c for c in r['cases']};assert all(c['registered'] for c in cases.values())
assert cases['append']['rows']==[{'v':10}] and cases['append']['fresh_path_rows']==[{'foo':9},{'foo':10}]
assert not cases['delete']['run_returned'] and cases['delete']['rows']==[] and 'FAILED_READ_FILE.FILE_NOT_EXIST' in str(cases['delete'])
assert cases['replace']['rows']==[{'v':12}] and cases['replace']['fresh_path_rows']==[{'foo':11}]
for c,k,n in [('append','files_at_registration','original.parquet'),('append','files_at_run','added.parquet'),('replace','files_at_run','replacement.parquet')]:assert digest(HERE/'spark-frozen-files/inputs'/n)==cases[c][k]['original.parquet' if c=='replace' else n]
r=load('public/receipt.json');assert r['sail_commit']==final and r['before']==r['after'] and r['outcome']=='passed'
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0} and r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(c['exit_code']==0 for c in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert comparison['dynamic']['matched']==13 and comparison['namespace']['matched']==3
assert comparison['expression']['matched']==0 and comparison['expression']['different']==2
print('PASS exact native94+176 / SDP94+177, independent unchanged lookup/namespace controls, fresh300+67, dynamic13/13, namespace3/3 and frozen-file design oracle; full goal open')
