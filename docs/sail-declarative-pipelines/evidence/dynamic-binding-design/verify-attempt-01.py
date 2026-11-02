from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent;SAIL='/Users/alexy/src/sail-pipelines-proposal';FINAL='ccb6fb21240b1b4d2962da833a74a17ade5e84c3'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',SAIL,*a],text=True).strip()
m=json.loads((HERE/'SHA256.json').read_text());assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for p,h in m.items():assert digest(HERE/p)==h
x=json.loads((HERE/'literal-ready/gate.json').read_text());c=json.loads((HERE/'literal-ready/candidate.json').read_text());assert x['sail_commit']==c['commit']==FINAL and x['outcome']=='passed'
assert git('rev-parse',FINAL+'^')==c['base']=='95c32c055712995e06a56fc5c0a86d09bc3c954f'
for check in x['checks']:assert check['exit_code']==0 and digest(HERE/'literal-ready'/(check['name']+'.log'))==check['sha256']
assert list(map(int,re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'literal-ready/rust.log').read_text())))==[139,240,92,176,25,6]
x=json.loads((HERE/'literal-attempt-01/gate.json').read_text());assert [c['exit_code'] for c in x['checks']]==[0,0,101]
assert '24 passed; 1 failed;' in (HERE/'literal-attempt-01/rust.log').read_text() and 'found TABLESAMPLE' in (HERE/'literal-attempt-01/rust.log').read_text()
x=json.loads((HERE/'literal-control/control.json').read_text());assert x['base']==FINAL and x['exit_code']==101 and digest(HERE/'literal-control/control.log')==x['log_sha256']
assert '1 passed; 1 failed;' in (HERE/'literal-control/control.log').read_text()
test='crates/sail-sql-analyzer/src/query_identifier_tests.rs';assert git('rev-parse',FINAL+':'+test)==git('rev-parse',x['control']+':'+test)==x['test_blob']
x=json.loads((HERE/'public/receipt.json').read_text());assert x['sail_commit']==FINAL and x['before']==x['after'] and x['outcome']=='passed'
assert x['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0} and x['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(c['exit_code']==0 for c in x['checks']) and x['server_exit_code']==0 and x['remaining_listener_pids']==[]
for p,h in x['artifact_sha256'].items():assert digest(HERE/'public'/p)==h
for folder,probe,count in [('spark-dynamic','reference.py',13),('spark-dynamic-initial','reference-initial.py',9),('spark-relations','relations-reference.py',7),('spark-relations-six','relations-reference-six.py',6)]:
 x=json.loads((HERE/folder/'observations.json').read_text());assert x['spark_version']=='4.2.1' and len(x['cases'])==count and x['harness_sha256']==digest(HERE/probe)
x=json.loads((HERE/'spark-relations/observations.json').read_text());cases={c['name']:c for c in x['cases']}
assert not cases['parameter_local']['registered'] and cases['parameter_local']['registration_condition']=='TABLE_OR_VIEW_NOT_FOUND'
for n in ['scalar_used','scalar_nested']:assert any('DUPLICATE_FLOW_SQL_CONF' in e for e in cases[n]['events'])
for n in ['scalar_unused','unused_alias']:assert cases[n]['rows']==[{'value':2}]
assert cases['parameter_external_frozen']['catalog_rows_after_replacement']==[{'bar':10}] and cases['parameter_external_frozen']['rows']==[{'Foo':9}]
assert x['listener_after_stop']=={'exit_code':1,'stdout':''}
assert 'CANNOT_MODIFY_STATIC_CONFIG' in (HERE/'relations-attempt-01.log').read_text() and "missing 1 required positional argument: 'sql_conf'" in (HERE/'relations-attempt-02.log').read_text()
x=json.loads((HERE/'reference-source.json').read_text())
for f in x['files']:assert hashlib.sha256(subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',x['spark_commit']+':'+f['path']])).hexdigest()==f['sha256']
assert json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True))==json.loads((HERE/'comparison.json').read_text())
print('PASS exact678 Rust, unchanged1/1 control, fresh300+67, dynamic10/13 and frozen-reference design witness; full goal open')
