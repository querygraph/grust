from pathlib import Path
import hashlib,json,subprocess,re
P=Path(__file__).resolve().parent;R='/Users/alexy/src/sail-pipelines-proposal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads((P/p).read_text())
def git(*a):return subprocess.check_output(['git','-C',R,*a])
m=load('SHA256.json');assert {x['path'] for x in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for x in m['files']:assert sha(P/x['path'])==x['sha256']
c=load('candidate.json');commit='b48162de9c9ee9cf4f386fa7eb3ebf683601a64d';base='8a7bf8ca4d98d43437eb005dde5db5b1f024e13c'
assert c['commit']==commit and c['base']==base and git('rev-parse',commit+'^').decode().strip()==base
assert git('diff',base,commit)==(P/'source.patch').read_bytes()
assert sorted(git('diff','--name-only',base,commit).decode().splitlines())==sorted(c['paths']) and len(c['paths'])==3
r=load('gate.json');assert r['outcome']=='passed' and r['sail_commit']==commit and r['packages']==['sail-execution']
for x in r['checks']:assert x['exit_code']==0 and sha(P/(x['name']+'.log'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'rust.log').read_text())==['243']
for test in ['decimal_codec_preserves_all_captured_fields_and_values','decimal_codec_preserves_typed_error_vocabulary','decimal_codec_preserves_lazy_thunks_in_full_physical_round_trip','decimal_codec_rejects_malformed_and_out_of_range_fields']:
 assert test+' ... ok' in (P/'rust.log').read_text()
for name in ['fail-policy','range-policy','signed-scale','precision-range','scale-range']:
 r=load(name+'-control.json');assert r['base']==commit and r['exit_code']==101 and sha(P/(name+'-control.log'))==r['log_sha256']
 assert git('diff',commit,r['control'])==(P/(name+'-control.patch')).read_bytes()
 assert git('diff','--name-only',commit,r['control']).decode().strip()==r['path']
 assert git('rev-parse',commit+':'+r['test_path']).decode().strip()==git('rev-parse',r['control']+':'+r['test_path']).decode().strip()==r['test_blob']
 assert '0 passed; 1 failed;' in (P/(name+'-control.log')).read_text()
a=load('initial-checkpoint/candidate.json');g=load('initial-checkpoint/gate.json');assert g['outcome']=='passed' and g['sail_commit']==a['commit']
assert git('diff',a['base'],a['commit'])==(P/'initial-checkpoint/source.patch').read_bytes()
for x in g['checks']:assert x['exit_code']==0 and sha(P/'initial-checkpoint'/(x['name']+'.log'))==x['sha256']
proto='crates/sail-execution/proto/sail/plan/physical.proto';old=git('show',base+':'+proto).decode();new=git('show',commit+':'+proto).decode()
def fields(text):return [(t,n,int(i)) for t,n,i in re.findall(r'^\s*(\w+)\s+(\w+)\s*=\s*(\d+)\s*;',text,re.M)]
def variants(text):return fields(text[text.index('message ExtendedScalarUdf {'):text.index('message ExtendedStreamUdf {')])
assert variants(new)==variants(old)+[('SparkStringToDecimalUdf','spark_string_to_decimal',43)] and len(variants(old))==42
message=new[new.index('message SparkStringToDecimalUdf {'):];assert fields(message)==[('uint32','precision',1),('int32','scale',2),('bool','fail_on_error',3),('bool','allow_negative_scale',4)]
for path in ['crates/sail-plan/src/resolver/expression/cast.rs','crates/sail-plan/src/config.rs','crates/sail-function/src/scalar/spark_string_to_decimal.rs','crates/sail-function/src/scalar/spark_string_to_decimal/parse.rs','crates/sail-execution/src/proto/converter.rs','crates/sail-function/src/scalar/math/div_mod_lazy.rs']:
 assert git('rev-parse',base+':'+path)==git('rev-parse',commit+':'+path)
boundary=load('runtime-boundary.json');prior=json.loads((P.parent/'legacy-floating-cast/public-regression/receipt.json').read_text());assert boundary['qualified_cli_source_commit']==prior['sail_commit']=='63f5bd3b3f0f8bd9b23607161d5988df853a738c' and boundary['cli_sha256']==prior['cli_sha256'] and boundary['current_source_commit']==commit
peer=load('peer-review.json');full=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',peer['commit']+':'+peer['path']],text=True)
assert full[full.index(peer['section']):]==(P/'peer-review.md').read_text() and sha(P/'peer-review.md')==peer['extract_sha256']
print('PASS decimal wire243/fmt/strictClippy/five unchanged0/1 controls; tags1..42 preserved/tag43 added; four captured fields; no resolver/config/folding activation')
