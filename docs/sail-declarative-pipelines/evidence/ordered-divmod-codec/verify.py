from pathlib import Path
import json,hashlib,re,subprocess
P=Path(__file__).resolve().parent;ROOT='/Users/alexy/src/sail-pipelines-proposal'
def load(path):return json.loads((P/path).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',ROOT,*args],text=True).strip()
m=load('SHA256.json');assert {f['path'] for f in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in m['files']:assert sha(P/f['path'])==f['sha256']
generic='04f1e8cc79e73932829dd6130a67b280792ebfe9';codec='036dc6dde5e5111dbfcae94ec8a3afb9f323c84b';parent='c1befda7a8f29937c9bbc32d3f516379732e9eae'
for label,commit,base,count,paths in [('generic',generic,parent,235,2),('codec',codec,generic,239,5)]:
 c=load(label+'/candidate.json');assert c['commit']==commit and c['base']==base and len(c['paths'])==paths
 assert git('rev-parse',commit+'^')==base
 assert sorted(git('diff','--name-only',base,commit).splitlines())==sorted(c['paths'])
 assert subprocess.check_output(['git','-C',ROOT,'diff',base,commit])==(P/label/'source.patch').read_bytes()
 r=load(label+'/gate.json');assert r['sail_commit']==commit and r['outcome']=='passed' and r['packages']==['sail-execution']
 for x in r['checks']:assert x['exit_code']==0 and sha(P/label/(x['name']+'.log'))==x['sha256']
 assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/label/'rust.log').read_text())==[str(count)]
for label,name,commit in [('generic','retention-control',generic),('generic','limit-control',generic),('generic','prefix-control',generic),('codec','mode-control-final',codec)]:
 r=load(label+'/'+name+'.json');assert r['base']==commit and r['exit_code']==101 and sha(P/label/(name+'.log'))==r['log_sha256']
 assert '0 passed; 1 failed;' in (P/label/(name+'.log')).read_text()
 assert git('rev-parse',commit+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
 assert git('diff','--name-only',commit,r['control'])==r['path']
for name in ['partial_none_keeps_previous_lambda_outputs','resolution_includes_zero_and_last_allowed_steps','nonconvergent_parameter_resolution_is_bounded','parameter_counts_preserve_physical_optional_lambda_prefixes','staged_decode_does_not_invoke_failing_lambda_bodies']:
 assert f'staged_lambda_tests::{name} ... ok' in (P/'generic/rust.log').read_text() and f'staged_lambda_tests::{name} ... ok' in (P/'codec/rust.log').read_text()
for name in ['div_mod_lazy_codec_preserves_modes_bindings_and_structured_errors','div_mod_lazy_codec_preserves_operation_captures_and_nonprefix_parameter','div_mod_lazy_codec_keeps_failing_left_thunk_skipped','div_mod_lazy_codec_rejects_missing_and_overdeclared_lambdas']:
 assert f'div_mod_lazy_tests::{name} ... ok' in (P/'codec/rust.log').read_text()
for path in ['crates/sail-plan/src/function/scalar/math.rs','crates/sail-plan/src/resolver/constant.rs','crates/sail-function/src/scalar/math/div_mod_lazy.rs']:
 assert git('rev-parse',parent+':'+path)==git('rev-parse',codec+':'+path),path
proto='crates/sail-execution/proto/sail/plan/physical.proto';assert git('rev-parse',parent+':'+proto)==git('rev-parse',generic+':'+proto)
s=git('show',codec+':'+proto);assert 'SparkDivModLazyUdf div_mod_lazy = 13;' in s and 'message SparkDivModLazyUdf {\n  bool ansi_mode = 1;\n}' in s
for label,name in [('generic','attempt-01'),('codec','attempt-01'),('codec','attempt-02')]:
 r=load(label+'/'+name+'/gate.json');assert any(x['exit_code']!=0 for x in r['checks'])
assert '230 passed; 3 failed;' in (P/'codec/attempt-02/rust.log').read_text()
for label,name,count in [('generic','checkpoint-01',235),('codec','checkpoint-01',234),('codec','checkpoint-02',234)]:
 r=load(label+'/'+name+'/gate.json');assert r['outcome']=='passed' and f'{count} passed; 0 failed;' in (P/label/name/'rust.log').read_text()
print('PASS generic235 + codec239 exact-source/fmt/strictClippy; four unchanged0/1 controls; retained failed/draft evidence; no lowering/constant/SQL activation')
