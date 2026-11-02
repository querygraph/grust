from pathlib import Path
import hashlib,json,re,subprocess
root='/Users/alexy/src/sail-sdp-gate';label='bounded-control-root-integration';offer='15e20669441ac09ee281704d78cc299e7fa1ccd0'
def git(*args):return subprocess.check_output(['git','-C',root,*args],text=True).strip()
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain') and c['base']=='f7c3482506342139cc3efb1267e12f31857a4f8b'
assert g['sail_commit']==c['commit']and g['outcome']=='passed'and g['packages']==['sail-common-datafusion','sail-spark-connect']
for x in g['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path(g['checks'][-1]['log']).read_text())==['134','83']
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])and len(c['paths'])==7
for p in c['paths']:assert git('rev-parse',c['commit']+':'+p)==git('rev-parse',offer+':'+p)
assert git('diff',c['base'],c['commit'],'--','Cargo.toml','Cargo.lock','crates/sail-common-datafusion/Cargo.toml')==''
print('PASS exact offered control/model blobs on contract+writer parent, combined134 common-datafusion+83 Connect libraries and strict gates '+c['commit'])
