from pathlib import Path
import hashlib,json,subprocess,sys
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads((P/p).read_text())
m=load('SHA256.json');assert {f['path'] for f in m['files']}=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for f in m['files']:assert sha(P/f['path'])==f['sha256']
for family,n in [('source-folding',56),('decimal-contract',192)]:
 s=load(family+'/spark/observations.json');a=load(family+'/public/observations.json')
 assert len(s['cases'])==len(a['cases'])==n and s['spark_version']==a['spark_version']=='4.2.1'
 assert s['spark_commit']=='617618396087429b5627a86ce933bb0f5d6645cb' and a['sail_commit']=='63f5bd3b3f0f8bd9b23607161d5988df853a738c'
 assert not s['remaining_listener_pids'] and not a['remaining_listener_pids']
 assert s['script_sha256']==sha(P/family/'spark.py') and a['script_sha256']==sha(P/family/'public.py') and a['spark_oracle_sha256']==sha(P/family/'spark/observations.json')
 for x in s['cases']+a['cases']:assert x['effective_ansi']==str(x['ansi']).lower()
for c in load('source-folding/spark/observations.json')['cases']:
 if c['case']=='identifier_null':assert not c['returned'] and c['phase']=='sql' and c['condition']=='NOT_A_CONSTANT_STRING.NULL'
 elif c['ansi'] and c['case'] in ['parquet_null','parquet_zero']:assert not c['returned'] and c['phase']=='explain' and c['condition']=='CAST_INVALID_INPUT' and c['sql_state']=='22018'
 elif c['case']=='case_branch_parquet':assert c['returned'] and c['rows'] in [[[1]],[['1.00']],[['1.0000000000']]]
 else:assert c['returned'] and c['rows']==[[None]]
decimal=load('decimal-contract/spark/observations.json')['cases'];cases={(c['ansi'],c['target'],c['is_try'],c['source']):c for c in decimal}
for target in ['DECIMAL(5,2)','DECIMAL(38,10)']:
 for source in ['１２.３','١٢.٣','1e٢','0e2147483647','0e2147483648','\x001.2\x00']:
  c=cases[True,target,False,source];assert c['returned']
 c=cases[True,target,False,'\u00a01.2\u00a0'];assert not c['returned'] and c['condition']=='CAST_INVALID_INPUT'
for source,condition in [('bad','CAST_INVALID_INPUT'),('999.995','NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION'),('1e400','NUMERIC_OUT_OF_SUPPORTED_RANGE')]:
 c=cases[True,'DECIMAL(5,2)',False,source];assert not c['returned'] and c['condition']==condition
for source,value in [('1.235','1.24'),('1.245','1.25'),('-1.235','-1.24')]:assert cases[True,'DECIMAL(5,2)',False,source]['values']==[value]
for c in decimal:
 if c['is_try'] or not c['ansi']:assert c['returned']
peer=load('peer-review.json');assert subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',peer['commit']+':'+peer['path']])==(P/'peer-review.txt').read_bytes()
assert len([json.loads(x) for x in (P/'peer-probe12.jsonl').read_text().splitlines()])==56
assert len([json.loads(x) for x in (P/'peer-probe13.jsonl').read_text().splitlines()])==24
c=subprocess.run([sys.executable,str(P/'check-conformance.py')],capture_output=True,text=True);assert c.returncode==1 and c.stdout==(P/'conformance-failure.log').read_text()
assert 'source-folding matched 16 of 56' in c.stdout and 'decimal-contract matched 101 of 192' in c.stdout
print('PASS source/phase56 and decimal192 Spark/Sail evidence; failures retained; no source activation or full SDP acceptance')
