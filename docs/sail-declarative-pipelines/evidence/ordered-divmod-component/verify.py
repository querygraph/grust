from pathlib import Path
import hashlib,json,re,subprocess
P=Path(__file__).resolve().parent;ROOT='/Users/alexy/src/sail-pipelines-proposal'
def load(path):return json.loads((P/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',ROOT,*args],text=True).strip()
manifest=load('SHA256.json');assert {f['path'] for f in manifest['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in manifest['files']:assert digest(P/f['path'])==f['sha256']
c=load('native/candidate.json');assert c['commit']=='c1befda7a8f29937c9bbc32d3f516379732e9eae' and c['base']=='b857dabb74da0484b781c096f9a9cd6a78daaa5c'
assert git('rev-parse',c['commit']+'^')==c['base']
assert sorted(git('diff','--name-only',c['base'],c['commit']).splitlines())==sorted(c['paths']) and len(c['paths'])==4
assert subprocess.check_output(['git','-C',ROOT,'diff',c['base'],c['commit']])==(P/'source.patch').read_bytes()
for path in ['crates/sail-plan/src/function/scalar/math.rs','crates/sail-execution/src/proto/codec.rs','crates/sail-execution/src/proto/encode.rs','crates/sail-execution/src/proto/decode.rs','crates/sail-execution/proto/sail/plan/physical.proto']:
 assert git('rev-parse',c['base']+':'+path)==git('rev-parse',c['commit']+':'+path),path
r=load('native/gate.json');assert r['sail_commit']==c['commit'] and r['outcome']=='passed' and r['packages']==['sail-function']
for x in r['checks']:assert x['exit_code']==0 and digest(P/'native'/Path(x['log']).name.removeprefix('sail-sdp-lazy-divmod-'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'native/rust.log').read_text())==['402']
for test in ['right_first_null_zero_skip_and_no_replay','stops_at_first_row_error_before_later_right_operand','floating_zeros_nan_infinity_and_empty_batch','result_field_metadata_and_divisor_admission','optimizer_keeps_conditional_failure_and_captured_operation','identical_calls_keep_separate_volatile_thunk_evaluations']:
 assert f'div_mod_lazy_tests::{test} ... ok' in (P/'native/rust.log').read_text()
r=load('native/left-first-control-v2.json');assert r['base']==c['commit'] and r['exit_code']==101 and digest(P/'native/left-first-control-v2.log')==r['log_sha256']
assert '0 passed; 1 failed;' in (P/'native/left-first-control-v2.log').read_text()
assert git('rev-parse',c['commit']+':'+r['test_path'])==git('rev-parse',r['control']+':'+r['test_path'])==r['test_blob']
assert git('diff','--name-only',c['commit'],r['control'])=='crates/sail-function/src/scalar/math/div_mod_lazy.rs'
r=load('native/batch-probe-v2.json');assert r['base']==c['commit'] and r['exit_code']==0 and digest(P/'native/batch-probe-v2.log')==r['log_sha256'] and digest(P/'native/batch-probe.rs')==r['snippet_sha256']
s=(P/'native/batch-probe-v2.log').read_text();assert '1 passed; 0 failed;' in s and 'ERROR_SELECTION row=' in s and 'COST_DIAGNOSTIC shared_host=true profile=unoptimized' in s
assert 'l failed on row 0' in s and 'r failed on row 1' in s
assert git('diff','--name-only',c['commit'],r['probe'])=='crates/sail-function/src/scalar/math/div_mod_lazy_tests.rs'
r=load('spark-row-errors/observations.json');assert r['spark_version']=='4.2.1' and r['spark_source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert digest(P/'spark-row-errors/run.py')==r['script_sha256'] and r['remaining_listener_pids']=='' and len(r['cases'])==8
for x in r['cases']:
 assert x['effective_ansi']=='true' and x['effective_codegen']==str(x['codegen']).lower() and not x['returned']
 assert x['condition']==('CAST_INVALID_INPUT' if x['reverse'] else 'USER_RAISED_EXCEPTION')
for name in ['attempt-01','attempt-02','attempt-03']:
 r=load(name+'/gate.json');assert any(x['exit_code']!=0 for x in r['checks']) and r.get('outcome')!='passed'
for name in ['checkpoint-01','checkpoint-02']:
 r=load(name+'/gate.json');assert r['outcome']=='passed' and '401 passed; 0 failed;' in (P/name/'rust.log').read_text()
r=load('batch-probe-attempt-01/probe.json');assert r['exit_code']!=0 and digest(P/'batch-probe-attempt-01/probe.log')==r['log_sha256']
print('PASS ordered DivMod component402/fmt/strictClippy, unchanged right-first0/1, selected-batch error/cost diagnostic and Spark8; no lowering/codec/public activation claim')
