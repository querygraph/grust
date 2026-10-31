from pathlib import Path
import hashlib,json,re,subprocess,sys
P=Path(__file__).resolve().parent
R='/Users/alexy/src/sail-pipelines-proposal'
BASE='4070e895b69338eb19f22643f0e40815da89ff34'
def load(name):return json.loads((P/name).read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',R,*args])
manifest=load('SHA256.json')
assert {f['path'] for f in manifest['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in manifest['files']:assert sha((P/f['path']).read_bytes())==f['sha256']
for name,count in [('fastpath-release',1),('fastpath-zero-copy',1),('zero-copy-mask',1),('optimizer',1),('raw-replay',2),('attempt-01/probe',None)]:
 r=load(name+'.json');assert r['base']==BASE
 assert sha((P/(name+'.log')).read_bytes())==r['log_sha256']
 snippet=(P/(name+'.rs')).read_bytes();assert sha(snippet)==r['snippet_sha256']
 assert git('show',r['probe']+':'+r['path'])==git('show',BASE+':'+r['path'])+snippet
 patch='attempt-01/source.patch' if count is None else name+'.patch'
 assert git('diff',BASE,r['probe'])==(P/patch).read_bytes()
 assert git('diff','--name-only',BASE,r['probe']).decode().strip()==r['path']
 log=(P/(name+'.log')).read_text()
 if count is None:assert r['exit_code']==101 and 'error[E0308]' in log
 else:assert r['exit_code']==0 and f'test result: ok. {count} passed; 0 failed;' in log
for name in ['fastpath-release','fastpath-zero-copy']:
 r=load(name+'.json');assert '--release' in r['command']
 log=(P/(name+'.log')).read_text();assert 'l failed on row 0; selected_batch=Execution error: r failed on row 1' in log
 assert 'rows=1024 iterations=50 samples=5 statistic=median' in log
 assert len(re.findall(r'row_over_native=[\d.]+ selected_batch_over_native=[\d.]+',log))==1
release=(P/'fastpath-zero-copy.rs').read_text();masks=(P/'zero-copy-mask.rs').read_text()
assert release.split('\nfn selected_batch_probe')[0]==masks.split('\nfn selected_batch_probe')[0]
assert len(re.findall(r'^MASK_CASE .* matched=true$',(P/'zero-copy-mask.log').read_text(),re.M))==18
raw=(P/'raw-replay.log').read_text();assert 'RAW_POLICY_SUMMARY cases=25' in raw and 'RAW_POLICY_JOIN common_execution=true actual=false' in raw
r=load('transport-control.json');assert r['production_base']==BASE and r['base_probe']==load('raw-replay.json')['probe']
assert r['exit_code']==101 and sha((P/'transport-control.log').read_bytes())==r['log_sha256']
assert git('diff',r['base_probe'],r['control'])==(P/'transport-control.patch').read_bytes()
def section(commit):
 s=git('show',commit+':'+r['path']).decode();return s[s.index('#[test]\nfn raw_replay_error_policy_matrix_probe'):].rstrip()
assert section(r['base_probe'])==section(r['control'])
assert 'resource expected=false actual=true common_execution=true' in (P/'transport-control.log').read_text()
spark=load('spark-observations.json');sail=load('sail-observations.json')['cases'];comparison=load('conditional-cast-comparison.json')
assert spark['spark_version']=='4.2.1' and spark['spark_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert not spark['remaining_listener_pids'] and len(spark['cases'])==16 and len(sail)==48
assert spark['script_sha256']==sha((P/'spark-oracle.py').read_bytes())
keys=lambda c:(c['ansi'],c['target'],c['zero'])
oracle={keys(c):c for c in spark['cases']};assert len(oracle)==16
for c in oracle.values():
 assert c['effective_ansi']==str(c['ansi']).lower()
 if c['zero'] and c['ansi']:assert not c['returned'] and c['condition']=='CAST_INVALID_INPUT' and c['sql_state']=='22018'
 else:assert c['returned'] and c['rows']==1 and c['all_null']
actual={(keys(c),c['representation']):c for c in sail};assert len(actual)==48
counts={name:0 for name in ['resolved_sql','internal_literal','internal_column']}
for c in comparison['cases']:
 s=actual[keys(c),c['representation']];o=oracle[keys(c)]
 returned_match=s['returned']==o['returned']
 matched=returned_match and ((s.get('rows')==o.get('rows') and s.get('all_null')==o.get('all_null')) if o['returned'] else o['condition'] in s.get('error',''))
 assert c['matched']==matched
 counts[c['representation']]+=matched
assert counts=={'resolved_sql':8,'internal_literal':10,'internal_column':10}
p=subprocess.run([sys.executable,str(P/'check-conformance.py')],capture_output=True,text=True)
assert p.returncode==1 and 'mismatches: 20' in p.stdout
assert p.stdout==(P/'conformance-failure.log').read_text()
print('PASS immutable diagnostic evidence; optimized order/cost probes,18 masks,25+join raw errors,unchanged prototype control;20 required cast mismatches retained')
