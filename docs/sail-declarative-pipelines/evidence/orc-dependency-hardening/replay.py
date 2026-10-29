from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,hashlib
root=Path('/Users/alexy/src/orc-rust-sdp-gate');binary=root/'target/debug/sail-sdp-orc-dependency-probe';out=Path('/tmp/orc-sdp-metadata-replay');out.mkdir(exist_ok=True)
commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();reports=[]
def run(name,args,expected):
 result=subprocess.run([str(binary),*args],capture_output=True,text=True,timeout=30)
 (out/(name+'.stdout')).write_text(result.stdout);(out/(name+'.stderr')).write_text(result.stderr)
 assert result.returncode==expected and 'panicked' not in result.stderr,(name,result)
 reports.append({'name':name,'arguments':args,'exit_code':result.returncode})
for fixture in sorted(Path('/tmp/sail-sdp-orc-reference/data').glob('*/*.orc')):
 for mode in ['read','read-async']:run(fixture.parent.name+'-'+mode,[mode,str(fixture)],0)
for mode in ['read','read-async']:run('malformed-block-'+mode,[mode,'/tmp/sail-sdp-orc-malformed-block.orc'],1)
run('write',['write',str(out/'output')],0)
run('extras',['extras',str(out/'output/nullable.orc')],0)
report={'recorded_at':datetime.now(timezone.utc).isoformat(),'orc_commit':commit,'probe_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':reports,'scope':'Standalone library replay on detached modified ORC; no Sail adapter/runtime qualification'}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS eight Spark-file reads, two malformed-file errors, writer and range/projection replay')
