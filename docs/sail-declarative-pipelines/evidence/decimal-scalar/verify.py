from pathlib import Path
from decimal import Decimal
import json,hashlib,subprocess,re
P=Path(__file__).resolve().parent;R='/Users/alexy/src/sail-pipelines-proposal'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads((P/p).read_text())
def git(*a):return subprocess.check_output(['git','-C',R,*a])
m=load('SHA256.json');assert {x['path'] for x in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for x in m['files']:assert sha(P/x['path'])==x['sha256']
c=load('candidate.json');commit='8a7bf8ca4d98d43437eb005dde5db5b1f024e13c';base='63f5bd3b3f0f8bd9b23607161d5988df853a738c'
assert c['commit']==commit and c['base']==base and git('rev-parse',commit+'^').decode().strip()==base
assert git('diff',base,commit)==(P/'source.patch').read_bytes()
assert len(git('diff','--name-only',base,commit).decode().splitlines())==11
r=load('gate.json');assert r['outcome']=='passed' and r['sail_commit']==commit and r['packages']==['sail-function']
for x in r['checks']:assert x['exit_code']==0 and sha(P/(x['name']+'.log'))==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'rust.log').read_text())==['410']
for name in ['rounding','trim','policy','nullable']:
 r=load(name+'-control.json');assert r['base']==commit and r['exit_code']==101 and sha(P/(name+'-control.log'))==r['log_sha256']
 assert git('diff',commit,r['control'])==(P/(name+'-control.patch')).read_bytes()
 assert git('diff','--name-only',commit,r['control']).decode().strip()==r['path']
 for p,b in r['test_blobs'].items():assert git('rev-parse',commit+':'+p).decode().strip()==git('rev-parse',r['control']+':'+p).decode().strip()==b
 assert '0 passed; 1 failed;' in (P/(name+'-control.log')).read_text()
for name,passed in [('attempt-01',False),('attempt-02',False),('checkpoint-409',True)]:
 d=P/name;a=json.loads((d/'candidate.json').read_text());g=json.loads((d/'gate.json').read_text())
 assert git('diff',a['base'],a['commit'])==(d/'source.patch').read_bytes()
 for x in g['checks']:assert sha(d/(x['name']+'.log'))==x['sha256']
 assert (g.get('outcome')=='passed')==passed
 if passed:assert '409 passed; 0 failed;' in (d/'rust.log').read_text()
spark=json.loads((P.parent/'source-dependent-cast-folding/decimal-contract/spark/observations.json').read_text())
policy=load('spark-policy/observations.json');assert len(spark['cases'])==192 and len(policy['cases'])==32
assert policy['spark_version']=='4.2.1' and policy['spark_commit']=='617618396087429b5627a86ce933bb0f5d6645cb' and not policy['remaining_listener_pids']
assert policy['script_sha256']==sha(P/'spark-policy.py')
def golden(record):
 p,s=map(int,record['target'][8:-1].split(','));value=None
 if record['returned'] and record['values'][0] is not None:
  t=Decimal(record['values'][0]).as_tuple();coefficient=int(''.join(map(str,t.digits)));exponent=t.exponent+s
  assert exponent>=0 or coefficient%10**(-exponent)==0
  value=(coefficient*10**exponent if exponent>=0 else coefficient//10**(-exponent))*(-1 if t.sign else 1)
 return {'source':record['source'],'precision':p,'scale':s,'fail_on_error':record['ansi'] and not record['is_try'],'allow_negative_scale':record.get('allow_negative_scale',False),'expected':value,'condition':record.get('condition'),'sql_state':record.get('sql_state'),'parameters':record.get('parameters',{})}
prefix='crates/sail-function/src/scalar/spark_string_to_decimal'
for records,file,n in [(spark['cases'],'contract.json',96),(policy['cases'],'policy-contract.json',32)]:
 expected={}
 for record in records:
  assert record['effective_ansi']==str(record['ansi']).lower()
  row=golden(record);key=(row['source'],row['precision'],row['scale'],row['fail_on_error'],row['allow_negative_scale'])
  if key in expected:assert expected[key]==row
  expected[key]=row
 fixture=json.loads(git('show',commit+':'+prefix+'/tests/'+file));assert len(fixture)==n
 actual=[{**row,'allow_negative_scale':row.get('allow_negative_scale',False)} for row in fixture]
 assert actual==list(expected.values())
for record in policy['cases']:assert record['effective_allow_negative_scale']==str(record['allow_negative_scale']).lower()
j=load('java-audit.json');assert j['source_sha256']==sha(P/'SdpDecimalDigits.java') and j['mapping_sha256']==sha(P/'java-digit-mapping.json')
assert git('show',commit+':'+prefix+'/tests/digit-mapping.json')==(P/'java-digit-mapping.json').read_bytes()
parsed=load('java-digit-mapping.json');assert parsed['java_version']=='20.0.2' and parsed['bmp_mapping_verified'] and len(parsed['starts'])==37
peer=load('peer-review.json');full=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',peer['commit']+':'+peer['path']],text=True)
assert full[full.index(peer['section']):]==(P/'peer-review.md').read_text() and sha(P/'peer-review.md')==peer['extract_sha256']
java17=load('java17-digit-mapping.json');assert java17['starts']==parsed['starts'] and java17['bmp_mapping_verified'] and sha(P/'java17-digit-mapping.json')==load('java17-audit.json')['mapping_sha256']
for path in ['crates/sail-plan/src/resolver/expression/cast.rs','crates/sail-execution/src/proto/codec.rs','crates/sail-execution/proto/sail/plan/physical.proto','crates/sail-function/src/scalar/math/div_mod_lazy.rs']:
 assert git('rev-parse',base+':'+path)==git('rev-parse',commit+':'+path)
print('PASS decimal component410/fmt/strictClippy/four unchanged0/1 controls; lossless Spark192+32 fixture mapping; Java BMP audit; no wire/resolver/replay activation')
