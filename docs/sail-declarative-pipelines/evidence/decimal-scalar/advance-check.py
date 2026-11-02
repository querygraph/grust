from pathlib import Path
import json,hashlib,subprocess
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-decimal-scalar-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-decimal-scalar-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for x in r['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '410 passed; 0 failed;' in Path('/tmp/sail-sdp-decimal-scalar-rust.log').read_text()
for name in ['rounding','trim','policy','nullable']:
 r=json.loads(Path('/tmp/sail-sdp-decimal-scalar-'+name+'-control.json').read_text());assert r['base']==c['commit'] and r['exit_code']==101
 log=Path('/tmp/sail-sdp-decimal-scalar-'+name+'-control.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==r['log_sha256'] and '0 passed; 1 failed;' in log.read_text()
 assert subprocess.check_output(['git','-C',R,'diff','--name-only',r['base'],r['control']],text=True).strip()==r['path']
 for p,b in r['test_blobs'].items():assert subprocess.check_output(['git','-C',R,'rev-parse',r['control']+':'+p],text=True).strip()==b
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
assert subprocess.check_output(['git','-C',R,'rev-parse','HEAD'],text=True).strip()==c['base']
print('PASS scalar component410/fmt/strictClippy/four unchanged0/1 controls; no resolver/wire/SQL activation')
