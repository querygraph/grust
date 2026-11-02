from pathlib import Path
import json,hashlib,re,subprocess
P=Path('/tmp');root='/Users/alexy/src/sail-pipelines-proposal'
c=json.loads((P/'sail-sdp-staged-lambda-decoder-candidate.json').read_text());r=json.loads((P/'sail-sdp-staged-lambda-decoder-gate.json').read_text())
assert c['base']=='c1befda7a8f29937c9bbc32d3f516379732e9eae' and c['commit']=='04f1e8cc79e73932829dd6130a67b280792ebfe9' and len(c['paths'])==2
assert r['sail_commit']==c['commit'] and r['outcome']=='passed' and r['packages']==['sail-execution']
for x in r['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (P/'sail-sdp-staged-lambda-decoder-rust.log').read_text())==['235']
for name in ['retention','limit','prefix']:
 r=json.loads((P/('sail-sdp-staged-lambda-decoder-'+name+'-control.json')).read_text());log=P/('sail-sdp-staged-lambda-decoder-'+name+'-control.log')
 assert r['base']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log.read_bytes()).hexdigest()==r['log_sha256'] and '0 passed; 1 failed;' in log.read_text()
 for commit in [r['base'],r['control']]:assert subprocess.check_output(['git','-C',root,'rev-parse',commit+':'+r['test_path']],text=True).strip()==r['test_blob']
 assert subprocess.check_output(['git','-C',root,'diff','--name-only',r['base'],r['control']],text=True).strip()==r['path']
assert subprocess.check_output(['git','-C','/Users/alexy/src/sail-sdp-gate','rev-parse','HEAD'],text=True).strip()==c['commit']
print('PASS staged lambda exact235/fmt/strictClippy/three unchanged0/1 controls; two-path generic unit, no new wire variant')
