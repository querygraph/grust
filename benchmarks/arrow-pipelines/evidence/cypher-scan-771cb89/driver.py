import datetime, hashlib, json, os, pathlib, subprocess, time
root = pathlib.Path('/Users/alexy/src/grust-arrow-pipeline')
os.chdir(root)
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
source = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
binary = root/'benchmarks/arrow-pipelines/target/release/cypher_scan'
assert binary.is_file()
receipt = pathlib.Path('/tmp/grust-cypher-scan-runs')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
receipt.mkdir(parents=True,exist_ok=False)
(receipt/'driver.py').write_bytes(pathlib.Path(__file__).read_bytes())
state = {'source':source,'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'host':subprocess.check_output(['uname','-a'],text=True).strip(),'runs':[],'complete':False}
print('RECEIPT',receipt,flush=True)
for nodes in [0,1,3,4,17,100000,1000000]:
 command=['/usr/bin/time','-l',str(binary),str(nodes),'3']
 start=time.monotonic()
 with (receipt/f'{nodes}.jsonl').open('w') as out, (receipt/f'{nodes}.stderr').open('w') as err:
  code=subprocess.run(command,stdout=out,stderr=err).returncode
 records=[json.loads(line) for line in (receipt/f'{nodes}.jsonl').read_text().splitlines()]
 trials=[r for r in records if r.get('event')=='trial']
 configs=[r for r in records if r.get('event')=='configuration']
 passed=code==0 and len(trials)==6 and all(r['status']=='pass' for r in trials) and len(configs)==1 and configs[0]['source']==source
 state['runs'].append({'nodes':nodes,'command':command,'exit_code':code,'seconds':time.monotonic()-start,'passed':passed})
 (receipt/'status.json').write_text(json.dumps(state,indent=2)+'\n')
 print('DONE',nodes,code,passed,flush=True)
 if not passed: raise SystemExit(1)
state['complete']=True
(receipt/'status.json').write_text(json.dumps(state,indent=2)+'\n')
