from pathlib import Path
from datetime import datetime, timezone
import subprocess, hashlib, json, itertools, os
root=Path('/Users/alexy/src/grust-sdp')
p=root/'docs/sail-declarative-pipelines/evidence/fable-c1-parser-oracle';p.mkdir()
repo='/Users/alexy/src/sail-pipelines-proposal';commit='49f32b65d438e7115fd5918f7398611ec6154f7a'
source=subprocess.check_output(['git','-C',repo,'show',commit+':crates/sail-spark-connect/src/pipelines/autocdc/attribute.rs'])
(p/'offered-attribute.rs').write_bytes(source)
rust='''use std::io::{self, BufRead};
type SparkResult<T> = Result<T, ()>;
mod errors { pub fn invalid_attribute_name_syntax(_: &str) {} }
'''+source.decode().split('pub(super) fn',1)[1].join(['fn',''])
# Only the offered function is used; Sail-specific error construction is stubbed.
rust+='''
fn main() { for line in io::stdin().lock().lines() { let line=line.unwrap(); let bytes: Vec<u8>=(0..line.len()).step_by(2).map(|i|u8::from_str_radix(&line[i..i+2],16).unwrap()).collect(); let name=String::from_utf8(bytes).unwrap(); match parse_attribute_name(&name) { Ok(parts)=>println!("OK:{}",parts.iter().map(|s|s.as_bytes().iter().map(|b|format!("{b:02x}")).collect::<String>()).collect::<Vec<_>>().join(",")), Err(_)=>println!("ERR") } } }
'''
(p/'parser-probe.rs').write_text(rust)
java='''import java.io.*; import java.nio.charset.StandardCharsets; import java.util.*;
public class AttributeProbe { public static void main(String[] args) throws Exception {
var reader=new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
for(String line;(line=reader.readLine())!=null;) { String name=new String(HexFormat.of().parseHex(line),StandardCharsets.UTF_8);
try { var parts=org.apache.spark.sql.catalyst.util.AttributeNameParser$.MODULE$.parseAttributeName(name).iterator(); var result=new ArrayList<String>(); while(parts.hasNext()) result.add(HexFormat.of().formatHex(parts.next().getBytes(StandardCharsets.UTF_8))); System.out.println("OK:"+String.join(",",result)); } catch(Exception e) {System.out.println("ERR");} }
} }
'''
(p/'AttributeProbe.java').write_text(java)
jars=sorted(Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars').glob('*.jar'));cp=os.pathsep.join(map(str,jars))
cases=[''.join(x) for n in range(6) for x in itertools.product(['a','.', '`',' ','é','𐐀'],repeat=n)]
cases+=['a\nb','`a\r\nb`','`a``b`.c','``.``','\x00','`𐐀.é`','a\t.b']
(p/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n');inputs=''.join(s.encode().hex()+'\n' for s in cases).encode()
build=Path('/tmp/sail-sdp-c1-parser-build');build.mkdir()
commands=[['rustc','+1.98.1',str(p/'parser-probe.rs'),'-o',str(build/'parser-probe')],['/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin/javac','-cp',cp,'-d',str(build),str(p/'AttributeProbe.java')]]
for i,cmd in enumerate(commands):
 r=subprocess.run(cmd,capture_output=True);(p/f'compile-{i}.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr).decode()
results=[]
for name,cmd in [('rust',[str(build/'parser-probe')]),('java',['/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin/java','-cp',str(build)+os.pathsep+cp,'AttributeProbe'])]:
 r=subprocess.run(cmd,input=inputs,capture_output=True);assert r.returncode==0;rout=r.stdout.decode().splitlines();assert len(rout)==len(cases);results.append(rout);(p/(name+'.stdout')).write_bytes(r.stdout);(p/(name+'.stderr')).write_bytes(r.stderr);commands.append(cmd)
mismatches=[{'input':s,'rust':a,'spark':b} for s,a,b in zip(cases,*results) if a!=b]
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'offered_commit':commit,'cases':len(cases),'mismatches':mismatches,'scope':'Exact offered parser function with stubbed Sail error construction versus installed Spark AttributeNameParser; compares acceptance and parts only, not error metadata, handler precedence or public CDC reachability','commands':commands,'jars':[{'path':str(j),'sha256':hashlib.sha256(j.read_bytes()).hexdigest()} for j in jars]}
(p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');assert not mismatches,mismatches[:10]
print('PASS',len(cases),'exact-function/JVM parser comparisons')
