from pathlib import Path
import json,hashlib,re,subprocess
P=Path(__file__).resolve().parent;ROOT='/Users/alexy/src/sail-pipelines-proposal'
def load(path):return json.loads((P/path).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',ROOT,*args],text=True).strip()
m=load('SHA256.json');assert {f['path'] for f in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in m['files']:assert sha(P/f['path'])==f['sha256']
c=load('candidate.json');commit='4070e895b69338eb19f22643f0e40815da89ff34';base='036dc6dde5e5111dbfcae94ec8a3afb9f323c84b'
assert c['commit']==commit and c['base']==base and len(c['paths'])==3 and git('rev-parse',commit+'^')==base
assert sorted(git('diff','--name-only',base,commit).splitlines())==sorted(c['paths'])
assert subprocess.check_output(['git','-C',ROOT,'diff',base,commit])==(P/'source.patch').read_bytes()
r=load('gate.json');assert r['sail_commit']==commit and r['outcome']=='passed' and r['packages']==['sail-plan']
for x in r['checks']:assert x['exit_code']==0 and sha(P/(x['name']+'.log'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'rust.log').read_text())==['114']
for name in ['admission','scope','volatile','async']:
 r=load(name+'-control.json');assert r['base']==commit and r['exit_code']==101 and sha(P/(name+'-control.log'))==r['log_sha256'] and '0 passed; 1 failed;' in (P/(name+'-control.log')).read_text()
 assert git('rev-parse',commit+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
 assert git('diff','--name-only',commit,r['control'])==r['path']
for name in ['internal_constants_validate_then_evaluate_with_existing_literal_path','nested_evaluators_shadow_names_and_preserve_outer_bindings','lambda_bindings_end_at_each_body_and_argument','volatile_and_provenance_descendants_reject_without_invocation','immutable_async_functions_remain_nonconstant_inside_each_scope','only_exact_evaluator_and_direct_argument_shapes_are_admitted','eligible_expressions_preserve_type_null_and_error_evaluation_phases']:
 assert f'validation_tests::{name} ... ok' in (P/'rust.log').read_text()
old=git('show',base+':crates/sail-plan/src/resolver/constant.rs');old=old[old.index('let non_constant = expression.exists('):];old=old[:old.index('Expr::ScalarFunction')]
new=git('show',commit+':crates/sail-plan/src/resolver/constant/validation.rs');ordinary=new[:new.index('Expr::ScalarFunction')]
assert set(re.findall(r'Expr::(\w+)\(\.\.\)',old))==set(re.findall(r'Expr::(\w+)\(\.\.\)',ordinary))
assert 'function.func.signature().volatility != Volatility::Volatile' in new and 'function.func.as_async().is_none()' in new
for path in ['crates/sail-plan/src/function/scalar/math.rs','crates/sail-plan/src/resolver/expression/cast.rs','crates/sail-execution/src/proto/converter.rs','crates/sail-execution/proto/sail/plan/physical.proto','crates/sail-function/src/scalar/math/div_mod_lazy.rs']:
 assert git('rev-parse',base+':'+path)==git('rev-parse',commit+':'+path),path
print('PASS scoped constants114/fmt/strictClippy/four unchanged0/1 controls; ordinary variant parity, exact internal lexical scopes, no lowering/codec/evaluation-policy activation')
