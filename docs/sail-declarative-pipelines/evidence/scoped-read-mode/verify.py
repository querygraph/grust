from pathlib import Path
import hashlib,json,subprocess,re
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('native/scoped-read-mode-02/candidate.json');commit=c['commit'];g=read('native/scoped-read-mode-02/gate.json')
assert g['outcome']=='passed' and g['sail_commit']==commit and g['packages']==['sail-plan','sail-spark-connect']
for check in g['checks']:assert check['exit_code']==0 and sha(E/'native/scoped-read-mode-02'/(check['name']+'.log'))==check['sha256']
log=(E/'native/scoped-read-mode-02/rust.log').read_text();assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',log)==['125','228']
f=read('native/scoped-read-mode-01/gate.json');assert f['checks'][-1]['exit_code']!=0 and 'is never used'in(E/'native/scoped-read-mode-01/clippy.log').read_text()
for path in c['paths']:assert (E/'source'/path).read_bytes()==subprocess.check_output(['git','-C',S,'show',commit+':'+path])
p=read('public/receipt.json');assert p['outcome']=='passed' and p['sail_commit']==commit and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
a=read('previous-runtime.json');b=read('runtime/observations.json');assert a['runtime_commit']==c['base'] and b['runtime_commit']==commit and b['cli_sha256']==p['cli_sha256'] and b['probe_completed'] and not b['remaining_listeners'] and b['server_exit_code']==0
assert len(a['cases'])==len(b['cases'])==12
for x,y in zip(a['cases'],b['cases']):
 for k in ['declared','read','missing','sql','outcome','condition','sql_state','parameters','message','direct','downstream','error_type','events']:assert x[k]==y[k],(k,x,y)
d=read('direct-context-spark/observations.json');assert d['probe_completed'] and len(d['cases'])==11 and not d['remaining_listeners']
assert d['cases'][0]['direct_typeof']=='time(3)' and d['cases'][0]['direct_schema']['fields'][0]['type']=='time(3)'
contexts=[o for case in d['cases']for o in case['observations']];assert len(contexts)==44
assert all(o['outcome']=='error' and '[ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION]'in o['message'] and 'schema'not in o for o in contexts)
f=read('framework-spark/observations.json');assert f['probe_completed'] and len(f['cases'])==72 and f['types_framework_default']=='false' and not f['remaining_listeners']
expected={
 'CAST(NULL AS TIME(3))':('TIME(3)','TIME(6)','TIME(3)'),
 'CAST(NULL AS TIME(6))':('TIME(6)','TIME(6)','TIME(6)'),
 "CAST('12:34:56.123' AS TIME(3))":('TIME(3)','TIME(6)','TIME(3)'),
 'CAST(NULL AS INTERVAL YEAR)':('INTERVAL YEAR','INTERVAL YEAR TO MONTH','INTERVAL YEAR TO MONTH'),
 'CAST(NULL AS INTERVAL MONTH)':('INTERVAL MONTH','INTERVAL YEAR TO MONTH','INTERVAL YEAR TO MONTH'),
 'CAST(NULL AS INTERVAL HOUR TO MINUTE)':('INTERVAL HOUR TO MINUTE','INTERVAL DAY TO SECOND','INTERVAL DAY TO SECOND'),
 'CAST(NULL AS ARRAY<TIME(3)>)':('ARRAY<TIME(3)>','ARRAY<TIME(6)>','ARRAY<TIME(3)>'),
 'CAST(NULL AS STRUCT<x:TIME(3)>)':('STRUCT<x: TIME(3)>','STRUCT<x: TIME(6)>','STRUCT<x: TIME(3)>'),
 'CAST(NULL AS ARRAY<INTERVAL YEAR>)':('ARRAY<INTERVAL YEAR>','ARRAY<INTERVAL YEAR TO MONTH>','ARRAY<INTERVAL YEAR TO MONTH>'),
}
seen=set()
for row in read('framework-summary.json'):
 key=tuple(row[k]for k in ['framework','expression','source_kind','streaming']);assert key not in seen;seen.add(key)
 reject=row['source_kind']=='TEMPORARY VIEW' and row['streaming'];assert row['view_rejected']==reject
 if reject:assert not row['observed_type']
 else:
  types=expected[row['expression']];index=(2 if row['framework']else 1)if row['streaming']else 0
  assert row['observed_type']==[types[index]],row
assert len(seen)==72
for row in read('reference.json'):
 data=subprocess.check_output(['git','-C',row['repository'],'show',row['commit']+':'+row['path']]);assert hashlib.sha256(data).hexdigest()==row['sha256']
print('PASS scoped read mode:125Plan+228Connect/fmt/Clippy/300+67;12diagnostics unchanged;72measured framework/read-mode cases;44context guard failures;projection not activated')
