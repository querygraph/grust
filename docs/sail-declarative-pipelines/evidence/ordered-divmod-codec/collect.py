from pathlib import Path
import json,shutil,subprocess
P=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/ordered-divmod-codec');P.mkdir(exist_ok=False)
def copy(source,target):
 s=Path(source);d=P/target
 if s.is_dir():shutil.copytree(s,d)
 else:d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s,d)
for label,names in [('generic',['candidate.json','gate.json','fmt.log','clippy.log','rust.log','controls.py','qualify.py','retention-control.json','retention-control.log','limit-control.json','limit-control.log','prefix-control.json','prefix-control.log']),('codec',['candidate.json','gate.json','fmt.log','clippy.log','rust.log','controls-final.py','mode-control-final.json','mode-control-final.log'])]:
 prefix='staged-lambda-decoder' if label=='generic' else 'lazy-divmod-codec'
 for name in names:copy('/tmp/sail-sdp-'+prefix+'-'+name,label+'/'+name)
 for name in (['attempt-01','checkpoint-01'] if label=='generic' else ['attempt-01','attempt-02','checkpoint-01','checkpoint-02']):copy('/tmp/sail-sdp-'+prefix+'-'+name,label+'/'+name)
 c=json.loads((P/label/'candidate.json').read_text());(P/label/'source.patch').write_bytes(subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','diff',c['base'],c['commit']]))
copy('/tmp/sail-sdp-ordered-divmod-codec-collect.py','collect.py')
print(P)
