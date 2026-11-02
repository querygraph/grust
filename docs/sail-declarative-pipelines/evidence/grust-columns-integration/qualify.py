from pathlib import Path
import json,subprocess,hashlib,tomllib
root=Path('/Users/alexy/src/sail-sdp-gate')
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True)
c=json.loads(Path('/tmp/sail-sdp-grust-columns-integration-candidate.json').read_text())
g=json.loads(Path('/tmp/sail-sdp-grust-columns-integration-gate.json').read_text())
assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
assert git('rev-parse','HEAD').strip()==c['commit'] and not git('status','--porcelain')
for check in g['checks']:
 assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
assert '16 passed; 0 failed' in Path('/tmp/sail-sdp-grust-columns-integration-rust.log').read_text()
base=tomllib.loads(git('show',c['base']+':Cargo.lock'))
current=tomllib.loads((root/'Cargo.lock').read_text())
assert [p for p in current['package'] if p['name']!='grust-columns']==base['package']
assert [p for p in current['package'] if p['name']=='grust-columns']==[{'name':'grust-columns','version':'0.1.0'}]
assert not any('grust-columns' in p.get('dependencies',[]) for p in current['package'])
m=json.loads((root/'vendor/grust-columns/SOURCE.json').read_text())
for name,h in m['files_sha256'].items():
 b=(root/'vendor/grust-columns'/name).read_bytes()
 original=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',m['commit']+':'+m['path']+'/'+name])
 assert b==original and hashlib.sha256(b).hexdigest()==h
subprocess.run(['/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','scripts/spark-pipelines-tests/verify_vendor.py'],cwd=root,check=True)
print('PASS immutable source identity, 16 tests and isolated lock delta '+c['commit'])
