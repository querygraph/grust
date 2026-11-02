from pathlib import Path
import json,subprocess,shutil
P=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/scoped-constant-validation');P.mkdir(exist_ok=False)
for name in ['candidate.json','gate.json','fmt.log','clippy.log','rust.log','controls.py','admission-control.json','admission-control.log','scope-control.json','scope-control.log','volatile-control.json','volatile-control.log','async-control.json','async-control.log']:
 shutil.copy2('/tmp/sail-sdp-scoped-constant-validation-'+name,P/name)
c=json.loads((P/'candidate.json').read_text());(P/'source.patch').write_bytes(subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','diff',c['base'],c['commit']]))
shutil.copy2('/tmp/sail-sdp-scoped-constant-validation-collect.py',P/'collect.py')
print(P)
