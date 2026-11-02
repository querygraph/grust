from pathlib import Path
import json,hashlib,subprocess
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-decimal-codec-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-decimal-codec-gate.json').read_text());assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for x in r['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert '243 passed; 0 failed;' in Path('/tmp/sail-sdp-decimal-codec-rust.log').read_text()
for name in ['fail-policy','range-policy','signed-scale','precision-range','scale-range']:
 r=json.loads(Path('/tmp/sail-sdp-decimal-codec-'+name+'-control.json').read_text());assert r['base']==c['commit'] and r['exit_code']==101
 log=Path('/tmp/sail-sdp-decimal-codec-'+name+'-control.log');assert hashlib.sha256(log.read_bytes()).hexdigest()==r['log_sha256'] and '0 passed; 1 failed;' in log.read_text()
 assert subprocess.check_output(['git','-C',R,'diff','--name-only',c['commit'],r['control']],text=True).strip()==r['path']
 assert subprocess.check_output(['git','-C',R,'rev-parse',r['control']+':'+r['test_path']],text=True).strip()==r['test_blob']
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
assert subprocess.check_output(['git','-C',R,'rev-parse','HEAD'],text=True).strip()==c['base']
print('PASS decimal wire243/fmt/strictClippy/five unchanged0/1 controls; direct physical-codec scope only')
