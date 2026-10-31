from pathlib import Path
import hashlib,json,re,subprocess
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit']
assert not any(s[k]for k in ['public_rerun','full_conformance','inventory_changed','sql_grammar_changed','client_error_classification_changed'])
g=read('native/sail-sdp-owned-parser-diagnostics-03-gate.json');assert g['sail_commit']==commit and g['outcome']=='passed'
assert set(g['packages'])=={'sail-sql-macro','sail-sql-parser','sail-sql-analyzer','sail-plan','sail-spark-connect'}
for c in g['checks']:assert c['exit_code']==0 and sha(E/'native'/Path(c['log']).name)==c['sha256']
log=(E/'native/sail-sdp-owned-parser-diagnostics-03-rust.log').read_text()
counts=list(map(int,re.findall(r'test result: ok\. (\d+) passed;',log)))
assert counts==s['native_counts'] and sum(counts)==s['native_total'] and len(counts)==5
assert sorted(counts)==[4,9,56,123,202] and s['native_total']==394
assert 'sql_failure_outlives_source_through_both_parse_routes ... ok' in log
syntax=read('native/sail-sdp-owned-parser-diagnostics-03-syntax.json')
assert syntax['sail_commit']==commit and syntax['exit_code']==0
assert sha(E/'native/sail-sdp-owned-parser-diagnostics-03-syntax.log')==syntax['log_sha256']
assert '1 passed; 0 failed;'in (E/'native/sail-sdp-owned-parser-diagnostics-03-syntax.log').read_text()
assert git('diff','--name-only',commit+'^',commit).decode().splitlines()==[
 'crates/sail-plan/src/error.rs','crates/sail-sql-analyzer/src/error.rs',
 'crates/sail-sql-analyzer/src/error/parser.rs','crates/sail-sql-analyzer/src/error/parser/tests.rs']
for old,passed in [('01',54),('02',55)]:
 initial=read('initial-'+old+'/sail-sdp-owned-parser-diagnostics-'+old+'-gate.json')
 assert initial['checks'][-1]['exit_code']==101 and initial['checks'][-1]['name']=='rust'
 for c in initial['checks']:assert sha(E/('initial-'+old)/Path(c['log']).name)==c['sha256']
 assert f'{passed} passed; 1 failed;' in (E/('initial-'+old)/('sail-sdp-owned-parser-diagnostics-'+old+'-rust.log')).read_text()
 assert git('diff','--name-only',initial['sail_commit'],commit).decode().strip()=='crates/sail-sql-analyzer/src/error/parser/tests.rs'
for label in ['token','context','display']:
 c=read('control-'+label+'.json');log=E/('control-'+label+'.log')
 assert c['base']==commit and c['exit_code']==101 and sha(log)==c['log_sha256'] and '0 passed; 1 failed;'in log.read_text()
 assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS owned parser diagnostics:'+str(s['native_total'])+'native/syntax/three controls;unchanged legacy errors,no new public runtime verdict')
