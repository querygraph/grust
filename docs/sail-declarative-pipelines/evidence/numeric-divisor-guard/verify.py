from pathlib import Path
import hashlib,json,re,subprocess
P=Path(__file__).resolve().parent
ROOT='/Users/alexy/src/sail-pipelines-proposal'
def load(p):return json.loads((P/p).read_text())
def git(*args):return subprocess.check_output(['git','-C',ROOT,*args],text=True).strip()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=load('SHA256.json')
assert {x['path'] for x in manifest['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in manifest['files']:assert digest(P/f['path'])==f['sha256']
c=load('native/candidate.json');commit=c['commit'];assert commit=='b857dabb74da0484b781c096f9a9cd6a78daaa5c'
assert git('rev-parse',commit+'^')==c['base']
assert sorted(git('diff','--name-only',c['base'],commit).splitlines())==sorted(c['paths'])
assert subprocess.check_output(['git','-C',ROOT,'diff',c['base'],commit])==(P/'source.patch').read_bytes()
n=load('native/gate.json');assert n['sail_commit']==commit and n['outcome']=='passed'
for x in n['checks']:assert x['exit_code']==0 and digest(P/'native'/Path(x['log']).name.removeprefix('sail-sdp-numeric-divisor-'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'native/rust.log').read_text())==['230','396','107','180']
for label in ['duplicate','codec']:
 r=load('native/'+label+'-control.json');assert r['base']==commit and r['exit_code']==101
 assert digest(P/'native'/str(label+'-control.log'))==r['log_sha256']
 assert '0 passed; 1 failed;' in (P/'native'/str(label+'-control.log')).read_text()
 assert git('rev-parse',commit+':'+r['test_path'])==r['test_blob']==git('rev-parse',r['control']+':'+r['test_path'])
 assert len(git('diff','--name-only',commit,r['control']).splitlines())==1
for directory,counts in [('stage-before',[1,1,6,7]),('native',[1,1,6,1])]:
 receipt='probe.json' if directory=='stage-before' else 'stage-probe.json';log='probe.log' if directory=='stage-before' else 'stage-probe.log'
 r=load(directory+'/'+receipt);assert r['exit_code']==0 and digest(P/directory/log)==r['log_sha256']
 s=(P/directory/log).read_text();assert [int(x) for x in re.findall(r'^COLLECT .*: (\d+) result=',s,re.M)]==counts
 assert set(re.findall(r'^(?:LOWER|FRAME) .*: (\d+)$',s,re.M))=={'0'}
 assert r['snippet_sha256']==digest(P/'stage-before/snippet.rs')
r=load('public/receipt.json');assert r['sail_commit']==commit and r['outcome']=='passed'
assert r['pytest']=={'tests':300,'errors':0,'failures':0,'skipped':0}
assert r['upstream']=={'tests_run':67,'errors':0,'failures':0,'skipped':0,'server_spark_version':'4.2.1'}
assert r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for x in r['checks']:assert x['exit_code']==0
for label in ['schema','runtime','domain','phases','arithmetic','provenance']:
 r=load(label+'/receipt.json');assert r['before']==r['after'] and r['before']['sail_commit']==commit
 assert r['before']['cli_sha256']==load('public/receipt.json')['cli_sha256']
 assert r['probe_exit_code']==r['server_exit_code']==0 and r['remaining_listener_pids']==[]
 for x in r['files']:assert digest(P/label/x['path'])==x['sha256']
report=load('native/comparison.json')
for label,total,behavior,metadata in [('schema',40,40,40),('runtime',12,6,6),('domain',2,0,0),('phases',48,33,13),('arithmetic',14,10,7),('provenance',20,19,11)]:
 v=report[label];assert (v['total'],v['behavior_matched'],v['metadata_matched'])==(total,behavior,metadata)
assert report['schema']['wire_matched']==40 and report['schema']['schema_matched']==33
prior=P.parent/'deferred-arithmetic'
for label,old in [('schema','candidate-schema'),('runtime','candidate-runtime'),('domain','domain-sail'),('phases','phases'),('arithmetic','arithmetic'),('provenance','provenance')]:
 a=json.loads((prior/old/'probe/observations.json').read_text().replace('/tmp/sail-sdp-deferred-arithmetic-phases','/tmp/sail-sdp-numeric-divisor-phases'))
 assert a['cases']==load(label+'/probe/observations.json')['cases'],label
attempt=load('attempt-01/gate.json');assert attempt['sail_commit']!=commit and attempt.get('outcome')!='passed' and any(x['exit_code']!=0 for x in attempt['checks'])
print('PASS numeric divisor exact-source913/native controls/public300+67/schema40; required runtime6/domain2 failures and generic CASE6 retained')
additional=load('additional-comparison.json');assert (additional['behavior_matched'],additional['metadata_matched'],additional['wire_matched'],additional['schema_matched'])==(16,20,20,7)
a=load('additional-parent/probe/observations.json');b=load('additional-sail-02/probe/observations.json')
assert len(a['cases'])==len(b['cases'])==22
spark=load('additional-spark-02/observations.json');changes=[]
for x,y,z in zip(a['cases'],b['cases'],spark['cases']):
 if x!=y:
  changes.append(x['name']);assert {k for k in x.keys()|y.keys() if x.get(k)!=y.get(k)}=={'schema'}
  assert y['schema']==z['schema'] and x['schema']!=z['schema']
assert changes==['legacy_decimal_mod','legacy_decimal_zero_mod']
r=load('parent-build.json');assert r['exit_code']==0 and r['sail_commit']==c['base'] and digest(P/'parent-build.log')==r['log_sha256']
r2=load('additional-parent/receipt.json');assert r2['before']==r2['after'] and r2['before']['sail_commit']==c['base'] and r2['before']['cli_sha256']==r['cli_sha256']
for label in ['additional-parent','additional-sail-02']:
 r=load(label+'/receipt.json');assert r['probe_exit_code']==r['server_exit_code']==0 and r['remaining_listener_pids']==[]
 for f in r['files']:assert digest(P/label/f['path'])==f['sha256']
failed=load('additional-sail/receipt.json');assert failed['probe_exit_code']==1 and failed['server_exit_code']==0 and failed['remaining_listener_pids']==[]
assert 'Object of type Decimal is not JSON serializable' in (P/'additional-sail/probe.log').read_text()
assert 'Object of type Decimal is not JSON serializable' in (P/'additional-spark.log').read_text()
print('PASS extra22 decimal/CASE/string rows/errors match parent; two legacy remainder schemas improve to Spark; gaps retained; failed recorder attempt preserved')

audit=load('string-mode-audit/observations.json');assert audit['spark_version']=='4.2.1' and audit['remaining_listener_pids']==''
assert len(audit['cases'])==16
for i,c in enumerate(audit['cases']):
 ansi=(i//4)%2==0;assert c['requested_ansi']==ansi and c['effective_ansi']==str(ansi).lower()
 if i%4<3 and ansi:assert not c['returned'] and c['condition']=='DATATYPE_MISMATCH.BINARY_OP_WRONG_TYPE'
 else:assert c['returned'] and c['rows']==([[None]] if i%4==1 else [[3.5]])
original=load('additional-spark-02/observations.json')['cases']
strings={c['name']:c for c in original if 'string_' in c['name']}
assert strings['legacy_string_zero']['rows']==[[None]] and strings['legacy_string_nonzero']['rows']==[[3.5]]
assert all(not strings[n]['returned'] for n in ['ansi_string_zero','ansi_string_nonzero'])
print('PASS string-mode correction: original observations and new effective-conf audit agree; raw comparison counts unchanged')
