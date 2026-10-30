from pathlib import Path
import hashlib,json,subprocess,textwrap
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-admission-root-integration-format';offer='8f953dbf02fea36565ae032a4c3087eaf39e0f61';prefix='crates/sail-spark-connect/src/pipelines/streaming/';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
def git(*args):return subprocess.check_output(['git','-C',repo,*args],text=True)
assert git('rev-parse','HEAD').strip()==c['base']
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',gate,'status','--porcelain'])
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text();assert 'test result: ok. 134 passed; 0 failed;' in log and 'test result: ok. 110 passed; 0 failed;' in log
original=git('show',offer+':'+prefix+'admission.rs');production,tests=original.split('#[cfg(test)]\nmod tests {\n');body=textwrap.dedent(tests[:-2]);expected='//! Tests for bounded logical-plan admission.\n\n'+body
expected=expected.replace('fn using(\n    builder: LogicalPlanBuilder,\n    right: LogicalPlan,\n    kind: JoinType,\n) -> DFResult<LogicalPlan> {','fn using(builder: LogicalPlanBuilder, right: LogicalPlan, kind: JoinType) -> DFResult<LogicalPlan> {')
assert git('show',c['commit']+':'+prefix+'admission.rs')==production+'#[cfg(test)]\n#[path = "admission_tests.rs"]\nmod tests;\n'
assert git('show',c['commit']+':'+prefix+'admission_tests.rs')==expected
assert git('show',c['commit']+':'+prefix+'binding.rs')==git('show',offer+':'+prefix+'binding.rs')
assert git('show',c['commit']+':'+prefix+'mod.rs')==git('show',c['base']+':'+prefix+'mod.rs').replace('pub(super) mod binding;','pub(super) mod admission;\npub(super) mod binding;')
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS corrected admission exact source/extracted tests/gates (134+110); binding field expectations removed')
