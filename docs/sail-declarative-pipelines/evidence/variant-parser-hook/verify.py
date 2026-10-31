from pathlib import Path
import hashlib,json,re,subprocess
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit'];gold='crates/sail-sql-parser/tests/gold_data/syntax.json'
assert not any(s[k]for k in ['public_rerun','full_conformance','inventory_changed','sql_grammar_changed'])
for label,counts in [('variant-parser-hook-03',[4,9]),('variant-hook-consumers-01',[52]),('variant-parser-hook-04',[4,9,52]),('syntax-golden-refresh-01',[6])]:
 g=read(label+'/sail-sdp-'+label+'-gate.json');assert g['outcome']=='passed'
 if label=='variant-parser-hook-04':assert g['sail_commit']==commit
 for c in g['checks']:assert c['exit_code']==0 and sha(E/label/Path(c['log']).name)==c['sha256']
 log=(E/label/('sail-sdp-'+label+'-rust.log')).read_text()
 assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',log)))==counts
for label in ['variant-parser-hook-01','variant-parser-hook-02']:
 g=read(label+'/sail-sdp-'+label+'-gate.json');assert g['checks'][-1]['name']=='clippy' and g['checks'][-1]['exit_code']==101
 for c in g['checks']:assert sha(E/label/Path(c['log']).name)==c['sha256']
 initial=g['sail_commit']
 assert git('diff','--name-only',initial,'29d41f794acd1fe2138c37f1856efb9c9ea936c1').decode().strip()=='crates/sail-sql-parser/src/tree/parser/tests.rs'
assert git('diff','--name-only','29d41f794acd1fe2138c37f1856efb9c9ea936c1',commit).decode().strip()==gold
refresh=s['syntax_refresh_commit'];assert git('diff','--name-only',refresh+'^',refresh).decode().strip()==gold
p=read('sail-sdp-syntax-golden-probe.json');assert p['same_generated_snapshot']
for c in p['checks']:
 assert sha(E/Path(c['log']).name)==c['sha256'] and c['exit_code']==(0 if c['update']else 101)
assert (E/'sail-sdp-syntax-candidate-generate.json').read_bytes()==(E/'sail-sdp-syntax-baseline-generate.json').read_bytes()
before=read('sail-sdp-syntax-golden-before.json');after=read('sail-sdp-syntax-baseline-generate.json')
assert len(before['tests'])==len(after['tests'])==1
for a,b in zip(before['tests'],after['tests']):assert {k:v for k,v in a.items()if k!='output'}=={k:v for k,v in b.items()if k!='output'}
assert git('show',commit+':'+gold)==(E/'sail-sdp-syntax-baseline-generate.json').read_bytes()
for receipt,log,rev,code in [('syntax.json','syntax.log','29d41f794acd1fe2138c37f1856efb9c9ea936c1',101),('sail-sdp-syntax-refresh-test.json','sail-sdp-syntax-refresh-test.log',refresh,0),('variant-parser-hook-04/sail-sdp-variant-parser-hook-04-syntax.json','variant-parser-hook-04/sail-sdp-variant-parser-hook-04-syntax.log',commit,0)]:
 r=read(receipt);assert r['sail_commit']==rev and r['exit_code']==code and sha(E/log)==r['log_sha256']
for label in ['dispatch','field-guard']:
 c=read(label+'-control.json');log=E/(label+'-control.log')
 assert c['base']==commit and c['exit_code']==101 and sha(log)==c['log_sha256'] and '0 passed; 1 failed;'in log.read_text()
 assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS variant hook65native/syntax/two controls;separate stale-golden repair6+1/baseline generation proof;no new public runtime claim')
