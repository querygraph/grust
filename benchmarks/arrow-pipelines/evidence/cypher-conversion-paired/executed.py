import datetime,json,pathlib,subprocess,hashlib
base=pathlib.Path('/tmp/grust-cypher-end-to-end-runs')
binaries={'before':base/'20260914T220926Z/cypher_end_to_end','after':base/'20260914T221312Z/cypher_end_to_end'}
receipt=pathlib.Path('/tmp/grust-conversion-paired')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');receipt.mkdir(parents=True)
(receipt/'executed.py').write_bytes(pathlib.Path(__file__).read_bytes())
state={'complete':False,'runs':[],'binaries':{k:{'path':str(v),'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for k,v in binaries.items()}}
print('RECEIPT',receipt,flush=True)
for pair in range(3):
 for name in (['before','after'] if pair%2==0 else ['after','before']):
  command=['nice','-n','10',str(binaries[name]),'1000000','3']
  with (receipt/f'{pair}-{name}.jsonl').open('w') as out:code=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT).returncode
  state['runs'].append({'pair':pair,'binary':name,'exit_code':code,'command':command})
  (receipt/'status.json').write_text(json.dumps(state,indent=2)+'\n')
  print('DONE',pair,name,code,flush=True)
state['complete']=True;(receipt/'status.json').write_text(json.dumps(state,indent=2)+'\n')
