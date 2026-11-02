from pathlib import Path
import hashlib,json,re,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='bounded-contract-root-integration';offer='44cbb94cc9eeac9d555f1a4136ee442fe8e8c7dd'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain') and c['base']=='7723dc4de8d3d8d4641b1445a8049345918fecb7'
assert g['sail_commit']==c['commit']and g['outcome']=='passed'and g['packages']==['sail-common-datafusion','sail-plan']
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path(g['checks'][-1]['log']).read_text())==['134','49']
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])and len(c['paths'])==2
for p in c['paths']:assert git('rev-parse',c['commit']+':'+p)==git('rev-parse',offer+':'+p)
assert git('diff',c['base'],c['commit'],'--','Cargo.toml','Cargo.lock','crates/sail-common-datafusion/Cargo.toml')==''
print('PASS exact offered contract/module blobs on writer parent, combined134 common-datafusion+49 plan libraries and strict gates '+c['commit'])
