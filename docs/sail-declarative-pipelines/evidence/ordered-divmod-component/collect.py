from pathlib import Path
import hashlib,json,shutil,subprocess
P=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/ordered-divmod-component');P.mkdir(exist_ok=False)
def copy(source,target):
 s=Path(source);d=P/target
 if s.is_dir():shutil.copytree(s,d)
 else:d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s,d)
for name in ['candidate.json','gate.json','fmt.log','clippy.log','rust.log','control-v2.py','left-first-control-v2.json','left-first-control-v2.log','batch-probe-v2.py','batch-probe-v2.json','batch-probe-v2.log','batch-probe.rs']:
 copy('/tmp/sail-sdp-lazy-divmod-'+name,'native/'+name)
for name in ['attempt-01','attempt-02','attempt-03','checkpoint-01','checkpoint-02','batch-probe-attempt-01']:copy('/tmp/sail-sdp-lazy-divmod-'+name,name)
copy('/tmp/sail-sdp-divmod-row-errors','spark-row-errors');copy('/tmp/sail-sdp-divmod-row-errors.py','spark-row-errors/run.py');copy('/tmp/sail-sdp-divmod-row-errors.log','spark-row-errors/run.log')
copy('/tmp/sail-sdp-lazy-divmod-collect.py','collect.py')
c=json.loads((P/'native/candidate.json').read_text());(P/'source.patch').write_bytes(subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','diff',c['base'],c['commit']]))
print(P)
