from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,hashlib,textwrap
root=Path('/Users/alexy/src/sail-sdp-gate')
label='root-lowercase-integration'
c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text())
g=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text())
assert g['outcome']=='passed' and g['sail_commit']==c['commit']
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True)
assert git('rev-parse','HEAD').strip()==c['commit'] and not git('status','--porcelain')
source='71e4a94d910c7afa978eaf1cc98beccb5df92051'
prefix='crates/sail-common/src/utils/'
original=git('show',source+':'+prefix+'root_lowercase.rs')
production,tests=original.split('#[cfg(test)]\nmod tests {\n',1)
actual=(root/prefix/'root_lowercase.rs').read_text()
assert actual==production+'#[cfg(test)]\n#[path = "root_lowercase_tests.rs"]\nmod tests;\n'
for name in ['root_lowercase_tables.rs','root_lowercase_oracle.json']:
 assert (root/prefix/name).read_text()==git('show',source+':'+prefix+name)
for check in g['checks']:
 assert check['exit_code']==0
 assert hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','CARGO_INCREMENTAL':'0','PYO3_PYTHON':'/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python','CARGO_TARGET_DIR':str(root/'target')}
command=['cargo','+1.98.1','test','-p','sail-common','--lib','--locked','optional_external_jvm_corpus_replays_against_the_helper','--','--nocapture']
packet=Path('/tmp/sail-sdp-root-lowercase-integration-extra');packet.mkdir()
corpus=Path('/tmp/sail-sdp-root-lowercase-integration-corpus.json')
malformed=packet/'malformed.json';malformed.write_text('{invalid JSON\n')
receipt={'sail_commit':c['commit'],'offered_source':source,'started_at':datetime.now(timezone.utc).isoformat(),'checks':[],'corpus_sha256':hashlib.sha256(corpus.read_bytes()).hexdigest(),'scope':'Exact common utility integration; no CDC caller or full SDP runtime claim'}
for name,path,expected in [('valid-corpus',corpus,0),('malformed-corpus',malformed,101),('missing-corpus',packet/'absent.json',101)]:
 log=packet/(name+'.log')
 with log.open('w') as out:r=subprocess.run(command,cwd=root,env={**env,'SAIL_FABLE_LOWERCASE_CORPUS':str(path)},stdout=out,stderr=subprocess.STDOUT)
 assert r.returncode==expected,(name,log.read_text())
 content=log.read_text()
 if expected==0:assert 'external corpus: 68588 strings, 0 mismatches' in content and '1 passed;' in content
 else:assert 'test result: FAILED' in content and 'the supplied JVM corpus should' in content
 receipt['checks'].append({'name':name,'command':command,'corpus':str(path),'expected_exit':expected,'actual_exit':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 print('PASS '+name+' expected exit '+str(expected),flush=True)
assert git('rev-parse','HEAD').strip()==c['commit'] and not git('status','--porcelain')
receipt['outcome']='passed';receipt['finished_at']=datetime.now(timezone.utc).isoformat()
(packet/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS exact source identity and explicit replay controls '+c['commit'])
