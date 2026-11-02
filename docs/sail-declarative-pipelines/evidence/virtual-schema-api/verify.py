from pathlib import Path
import hashlib,json,subprocess
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
c=read('native/sail-sdp-virtual-schema-api-02-candidate.json');g=read('native/sail-sdp-virtual-schema-api-02-gate.json');commit=c['commit']
assert g['outcome']=='passed' and g['sail_commit']==commit
for x in g['checks']:assert x['exit_code']==0 and sha(E/'native'/Path(x['log']).name)==x['sha256']
assert '221 passed; 0 failed;'in(E/'native/sail-sdp-virtual-schema-api-02-rust.log').read_text()
f=read('native-initial/sail-sdp-virtual-schema-api-gate.json');assert f['checks'][-1]['exit_code']!=0 and '220 passed; 1 failed;'in(E/'native-initial/sail-sdp-virtual-schema-api-rust.log').read_text()
p=read('public/receipt.json');assert p['sail_commit']==commit and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
a=read('previous-runtime.json');b=read('runtime/observations.json');assert a['runtime_commit']==c['base'] and b['runtime_commit']==commit and b['cli_sha256']==p['cli_sha256']
assert b['probe_completed'] and len(a['cases'])==len(b['cases'])==12 and not b['remaining_listeners'] and b['server_exit_code']==0
for x,y in zip(a['cases'],b['cases']):
 for field in ['declared','read','missing','sql','outcome','error_type','condition','sql_state','parameters','message','direct','downstream','events']:assert x[field]==y[field],(field,x,y)
 assert y['message'].startswith('[UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA]')
print('PASS virtual-schema APIs:221native/fmt/Clippy/300+67;12 runtime diagnostics unchanged and still divergent from Spark; lazy scope not activated')
