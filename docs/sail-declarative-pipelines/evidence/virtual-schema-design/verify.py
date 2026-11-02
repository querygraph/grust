from pathlib import Path
import hashlib,json,subprocess
E=Path(__file__).resolve().parent
repos={'spark':'/Users/alexy/src/spark-sdp-4.2.1','sail':'/Users/alexy/src/sail-pipelines-proposal'}
def read(p):return json.loads((E/p).read_text())
for f,h in read('MANIFEST.json').items():assert hashlib.sha256((E/f).read_bytes()).hexdigest()==h,f
for ref in read('sources.json'):
 data=subprocess.check_output(['git','-C',repos[ref['mode']],'show',ref['commit']+':'+ref['source']]);assert data==(E/ref['copy']).read_bytes() and hashlib.sha256(data).hexdigest()==ref['sha256']
a=read('spark/observations.json');b=read('sail/observations.json')
for r in [a,b]:assert r['probe_completed'] and len(r['cases'])==12 and r['version']=='4.2.1' and not r['remaining_listeners'] and r['script_sha256']==hashlib.sha256((E/'probe.py').read_bytes()).hexdigest()
p=read('accepted-cli-receipt.json');assert p['outcome']=='passed' and b['runtime_commit']==p['sail_commit']=='c64533302173f88087485a531306f34346732b5e' and b['cli_sha256']==p['cli_sha256'] and b['server_exit_code']==0
assert sum(x['direct']is not None for x in a['cases'])==9
assert sum(x['condition']=='CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE'for x in a['cases'])==3
for x,y in zip(a['cases'],b['cases']):
 assert all(x[k]==y[k]for k in ['declared','read','missing','sql'])
 assert y['message'].startswith('[UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA]')
 if x['missing']!='none':assert x['direct']==('consumer, late'if x['read']and not x['declared']else 'late')
assert len(read('comparison.json'))==12 and not any(x['matched']for x in read('comparison.json'))
print('Verified12 paired virtual-schema observations; all12 Sail conformance gaps preserved; design proposal only')
