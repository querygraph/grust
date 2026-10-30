from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess
p=Path('/tmp/sail-sdp-fable-kernel-rust-probe');p.mkdir()
java=json.loads(Path('/tmp/sail-sdp-fable-kernel-jvm-probe/results.json').read_text())
cases=[x for x in java if x['kind']=='lowercase']
def literal(s):return '"'+''.join('\\u{'+cp[2:]+'}' for cp in s.split())+'"'
source='fn main() {\n'
for c in cases:
 source+='    println!("'+c['case']+'\\t{}", '+literal(c['left_codepoints'])+'.to_lowercase() == '+literal(c['right_codepoints'])+'.to_lowercase());\n'
source+='}\n'
(p/'lowercase.rs').write_text(source)
commands=[('version',['rustc','+1.98.1','--version','--verbose']),('compile',['rustc','+1.98.1',str(p/'lowercase.rs'),'-o','/tmp/sail-sdp-fable-kernel-rust-probe-bin']),('run',['/tmp/sail-sdp-fable-kernel-rust-probe-bin'])]
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'scope':'Direct Rust str::to_lowercase comparison using the offered schema.rs expression; not a Sail/CDC execution test','commands':[]}
for label,command in commands:
 r=subprocess.run(command,capture_output=True,cwd=p)
 (p/(label+'.stdout.txt')).write_bytes(r.stdout);(p/(label+'.stderr.txt')).write_bytes(r.stderr)
 receipt['commands'].append({'label':label,'argv':command,'exit_code':r.returncode})
 (p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 assert r.returncode==0
actual=dict(line.split('\t') for line in (p/'run.stdout.txt').read_text().splitlines())
results=[{**c,'rust_lowercase_equal':actual[c['case']]=='true','differs_from_java':(actual[c['case']]=='true')!=c['root_lowercase_equal']} for c in cases]
(p/'results.json').write_text(json.dumps(results,indent=2)+'\n')
receipt['mismatches']=[c['case'] for c in results if c['differs_from_java']]
receipt['case_count']=len(cases)
receipt['source_sha256']=hashlib.sha256((p/'lowercase.rs').read_bytes()).hexdigest()
receipt['binary_sha256']=hashlib.sha256(Path('/tmp/sail-sdp-fable-kernel-rust-probe-bin').read_bytes()).hexdigest()
receipt['jvm_results_sha256']=hashlib.sha256(Path('/tmp/sail-sdp-fable-kernel-jvm-probe/results.json').read_bytes()).hexdigest()
receipt['completed_at']=datetime.now(timezone.utc).isoformat()
(p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'case_count':len(cases),'mismatches':receipt['mismatches']}))
