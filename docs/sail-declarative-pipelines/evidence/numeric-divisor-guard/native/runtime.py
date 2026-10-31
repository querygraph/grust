from pathlib import Path
import json,subprocess
ROOT='/Users/alexy/src/sail-pipelines-proposal';PYTHON=ROOT+'/.venv/bin/python'
c=json.loads(Path('/tmp/sail-sdp-numeric-divisor-candidate.json').read_text());qualified='/tmp/sail-sdp-numeric-divisor-public/receipt.json'
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence')
for packet,output,probe in [('deferred-arithmetic','schema','schema-reference.py'),('deferred-arithmetic','runtime','runtime-gap-reference.py'),('deferred-arithmetic','domain','input-domain-reference.py'),('wrapped-catalog-identifier','phases','reference.py'),('constant-context-lowering','arithmetic','reference.py'),('identifier-function-provenance','provenance','reference.py')]:
 subprocess.run([PYTHON,str(p/packet/'run-probe.py'),'/tmp/sail-sdp-numeric-divisor-'+output,c['commit'],qualified,'identifier',probe],check=True)
 print('PASS recorded '+output,flush=True)
subprocess.run([PYTHON,'/tmp/sail-sdp-numeric-divisor-controls.py'],check=True)
