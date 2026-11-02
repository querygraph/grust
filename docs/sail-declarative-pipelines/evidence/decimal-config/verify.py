from pathlib import Path
import json,hashlib,subprocess,re,tomllib,ast,os
P=Path(__file__).resolve().parent;R='/Users/alexy/src/sail-pipelines-proposal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads((P/p).read_text())
def git(*a):return subprocess.check_output(['git','-C',R,*a])
m=load('SHA256.json');assert {f['path'] for f in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in m['files']:assert sha(P/f['path'])==f['sha256']
c=load('candidate.json');commit='226b0c1cfc9ac72dadc3ec8a81667f7acc3aacec';base='b48162de9c9ee9cf4f386fa7eb3ebf683601a64d';assert c['commit']==commit and c['base']==base and len(c['paths'])==8
assert git('diff',base,commit)==(P/'source.patch').read_bytes() and sorted(git('diff','--name-only',base,commit).decode().splitlines())==sorted(c['paths'])
r=load('gate.json');assert r['outcome']=='passed' and r['sail_commit']==commit
for x in r['checks']:assert x['exit_code']==0 and sha(P/(x['name']+'.log'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'rust.log').read_text())==['117','183']
for name in ['capture','set-validation','java-trim','hierarchy']:
 r=load(name+'-control.json');assert r['base']==commit and r['exit_code']==101 and sha(P/(name+'-control.log'))==r['log_sha256']
 assert git('diff',commit,r['control'])==(P/(name+'-control.patch')).read_bytes() and git('diff','--name-only',commit,r['control']).decode().strip()==r['path']
 assert git('rev-parse',commit+':'+r['test_path']).decode().strip()==git('rev-parse',r['control']+':'+r['test_path']).decode().strip()==r['test_blob']
 assert '0 passed; 1 failed;' in (P/(name+'-control.log')).read_text()
for name in ['attempt-01','attempt-02']:
 a=load(name+'/candidate.json');g=load(name+'/gate.json');assert git('diff',a['base'],a['commit'])==(P/name/'source.patch').read_bytes()
 for x in g['checks']:assert sha(P/name/(x['name']+'.log'))==x['sha256']
 assert g['checks'][-1]['exit_code']!=0
assert load('attempt-02/candidate.json')['commit']==commit and '181 passed; 2 failed;' in (P/'attempt-02/rust.log').read_text()
e=load('env-control.json');assert e['sail_commit']==commit and e['exit_code']==0 and e['log_sha256']==sha(P/'env-control.log') and '1 passed; 0 failed;' in (P/'env-control.log').read_text()
expected={'PYTHONPATH':'/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages','VIRTUAL_ENV':'/Users/alexy/src/sail-pipelines-proposal/.venv'};assert load('gate-environment.json')['overrides']==expected
cargo='crates/sail-spark-connect/Cargo.toml';old=tomllib.loads(git('show',base+':'+cargo).decode());new=tomllib.loads(git('show',commit+':'+cargo).decode());assert old['dependencies']==new['dependencies'] and new['dev-dependencies']=={**old['dev-dependencies'],'sail-function':{'path':'../sail-function'}}
lock=git('show',base+':Cargo.lock').decode();a=lock.index('name = "sail-spark-connect"\n');b=lock.index('\n[[package]]',a);block=lock[a:b].replace(' "sail-execution",\n',' "sail-execution",\n "sail-function",\n');assert lock[:a]+block+lock[b:]==git('show',commit+':Cargo.lock').decode()
s=load('spark/observations.json');v=load('public/observations.json');assert s['spark_version']==v['spark_version']=='4.2.1' and s['spark_commit']=='617618396087429b5627a86ce933bb0f5d6645cb' and v['sail_commit']==commit
assert len(s['cases'])==len(v['cases'])==12 and not s['remaining_listener_pids'] and not v['remaining_listener_pids']
assert s['script_sha256']==sha(P/'spark.py') and v['script_sha256']==sha(P/'public.py') and v['spark_oracle_sha256']==sha(P/'spark/observations.json')
assert s['default']==v['default']==s['after_unset']==v['after_unset']=='false'
for o,a in zip(s['cases'],v['cases']):assert all(a.get(k)==value for k,value in o.items()) and a['query_rows']==[[1]]
p=load('public-regression/receipt.json');assert p['outcome']=='passed' and p['sail_commit']==commit and not p['remaining_listener_pids'] and p['cli_sha256']==v['cli_sha256']
for file,digest in p['artifact_sha256'].items():assert sha(P/'public-regression'/file)==digest
assert p['upstream']['tests_run']==67 and p['upstream']['failures']==p['upstream']['errors']==p['upstream']['skipped']==0
import xml.etree.ElementTree as ET
suite=ET.parse(P/'public-regression/pytest.xml').getroot().find('testsuite');assert suite is not None and (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('300','0','0','0')
for path in ['crates/sail-plan/src/resolver/expression/cast.rs','crates/sail-plan/src/resolver/data_type.rs','crates/sail-function/src/scalar/spark_string_to_decimal.rs','crates/sail-execution/src/proto/codec.rs','crates/sail-spark-connect/src/pipelines/streaming/lower.rs']:
 assert git('rev-parse',base+':'+path)==git('rev-parse',commit+':'+path)
peer=load('peer-review.json');full=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',peer['commit']+':'+peer['path']],text=True);assert full[full.index(peer['section']):]==(P/'peer-review.md').read_text() and sha(P/'peer-review.md')==peer['extract_sha256']
update=load('helper-update.json');assert update['old_helper_sha256']==sha(P/'old-library-gates.py') and update['new_helper_sha256']==sha(P/'new-library-gates.py')
node=next(x.value for x in ast.parse((P/'new-library-gates.py').read_text()).body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='env' for t in x.targets));env=eval(compile(ast.Expression(node),'<owned-gate-env>','eval'),{'os':os});assert all(env[k]==value for k,value in expected.items()) and env['PYO3_PYTHON']==e['overrides']['PYO3_PYTHON']
print('PASS config117+183/fmt/strictClippy/four unchanged0/1 controls/public300+67/config12; env-only failure control retained; no SQL cast/type/folding activation')
