from pathlib import Path
import subprocess,itertools,json,hashlib
from datetime import datetime,timezone
p=Path('/tmp/sail-sdp-c2-context-probe');p.mkdir();(p/'src').mkdir()
repo='/Users/alexy/src/sail-pipelines-proposal';commit='f4537586b6c79d60ebc56a183d9744948d812576'
for name in ['root_lowercase.rs','root_lowercase_tables.rs']:
 data=subprocess.check_output(['git','-C',repo,'show',commit+':crates/sail-common/src/utils/'+name]);(p/'src'/name).write_bytes(data)
(p/'Cargo.toml').write_text('[package]\nname="c2-context-probe"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nicu_casemap="=2.3.0"\nregex="=1.13.1"\n')
(p/'src/main.rs').write_text('''mod root_lowercase;
use std::io::{self,BufRead};
fn main(){for line in io::stdin().lock().lines(){let s=line.unwrap();let bytes:Vec<u8>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();let value=String::from_utf8(bytes).unwrap();let lower=root_lowercase::spark_root_lowercase(&value);println!("{}",lower.as_bytes().iter().map(|b|format!("{b:02x}")).collect::<String>());}}
''')
java=Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin')
(p/'RootProbe.java').write_text('''import java.io.*;import java.util.*;import java.nio.charset.StandardCharsets;
public class RootProbe{public static void main(String[] args)throws Exception{var reader=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));for(String line;(line=reader.readLine())!=null;){var s=new String(HexFormat.of().parseHex(line),StandardCharsets.UTF_8);System.out.println(HexFormat.of().formatHex(s.toLowerCase(Locale.ROOT).getBytes(StandardCharsets.UTF_8)));}}}
''')
with(p/'build.log').open('w')as log:subprocess.run(['cargo','+1.98.1','build','--offline','--manifest-path',str(p/'Cargo.toml')],stdout=log,stderr=subprocess.STDOUT,check=True)
subprocess.run([str(java/'javac'),str(p/'RootProbe.java')],check=True)
cases=[]
for n in range(6):
 for parts in itertools.product(['A','1','.',"'",'_','\u0301','\u200d'],repeat=n):
  s=''.join(parts);cases.extend(['AΣ'+s,'A'+s+'Σ'])
cases=list(dict.fromkeys(cases));(p/'cases.json').write_text(json.dumps(cases,ensure_ascii=False)+'\n');input=''.join(s.encode().hex()+'\n' for s in cases).encode();outputs=[]
commands=[['target/debug/c2-context-probe'],[str(java/'java'),'-cp',str(p),'RootProbe']]
for name,cmd in zip(['rust','java'],commands):
 r=subprocess.run(cmd,cwd=p,input=input,capture_output=True,check=True);(p/(name+'.stdout')).write_bytes(r.stdout);(p/(name+'.stderr')).write_bytes(r.stderr);outputs.append(r.stdout.decode().splitlines());assert len(outputs[-1])==len(cases)
mismatch=[{'input':s,'codepoints':[hex(ord(x))for x in s],'rust':bytes.fromhex(a).decode(),'java':bytes.fromhex(b).decode()}for s,a,b in zip(cases,*outputs)if a!=b]
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'commit':commit,'scope':'Exact offered Rust helper/tables in isolated minimal crate versus JDK17 ROOT lowercase, generated sigma contexts only; no Spark/CDC reachability claim','cases':len(cases),'mismatch_count':len(mismatch),'mismatches':mismatch,'commands':commands}
(p/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'cases':len(cases),'mismatches':len(mismatch),'first':mismatch[:6]},ensure_ascii=False))
