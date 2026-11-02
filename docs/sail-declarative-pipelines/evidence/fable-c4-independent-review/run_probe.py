from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib,itertools,random,os,shutil
p=Path('/tmp/sail-sdp-c4-independent-probe');p.mkdir(exist_ok=True);(p/'src/utils').mkdir(parents=True,exist_ok=True)
repo='/Users/alexy/src/sail-pipelines-proposal';commit='a495cb02d'
def source(path):return subprocess.check_output(['git','-C',repo,'show',commit+':'+path])
paths={'src/lookup.rs':'crates/sail-spark-connect/src/pipelines/autocdc/lookup.rs','src/utils/root_lowercase.rs':'crates/sail-common/src/utils/root_lowercase.rs','src/utils/root_lowercase_tables.rs':'crates/sail-common/src/utils/root_lowercase_tables.rs'}
for dest,path in paths.items():(p/dest).write_bytes(source(path))
(p/'Cargo.toml').write_text('[package]\nname="c4-independent-probe"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nicu_casemap="=2.3.0"\nregex="=1.13.1"\n')
(p/'src/main.rs').write_text('''extern crate self as sail_common;
mod utils {pub mod root_lowercase;}
mod schema {#[derive(Clone,Copy)] pub enum Case {Sensitive,Insensitive}}
mod lookup;
use std::io::{self,BufRead};
fn text(s:&str)->String{let bytes:Vec<u8>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();String::from_utf8(bytes).unwrap()}
fn main(){for line in io::stdin().lock().lines(){let s=line.unwrap();let mut items=s.split('\t');let n:usize=items.next().unwrap().parse().unwrap();let fields:Vec<String>=(0..n).map(|_|text(items.next().unwrap())).collect();let query=text(items.next().unwrap());let lookup=lookup::FieldLookup::new(&fields);let a=lookup.resolver(schema::Case::Sensitive)(&query).map(|x|x as i64).unwrap_or(-1);let b=lookup.resolver(schema::Case::Insensitive)(&query).map(|x|x as i64).unwrap_or(-1);println!("{a},{b}");}}
''')
(p/'src/main.rs').write_text((p/'src/main.rs').read_text().replace(chr(9),chr(92)+'t'))
# Retain the exact offered fixture before adding independent generated schemas.
fixture=source('crates/sail-spark-connect/src/pipelines/autocdc/lookup_oracle.json');(p/'offered-oracle.json').write_bytes(fixture)
cases=[{'origin':'offered','fields':c['fields'],'queries':[q['name'] for q in c['queries']]}for c in json.loads(fixture)['cases']]
rng=random.Random(20261030)
collisions=[''.join(x)for x in itertools.product(['Aa','BB'],repeat=4)]
pool=['','a','A','name','Name','NAME','\U00010400','\U00010428']+collisions+[f'c{i}'for i in range(80)]+[f'C{i}'for i in range(80)]
for _ in range(256):
 fields=[rng.choice(pool)for _ in range(rng.randrange(81))];queries=list(dict.fromkeys(fields+[s.swapcase()for s in fields]+['absent']))
 cases.append({'origin':'independent-seed-20261030','fields':fields,'queries':queries})
(p/'cases.json').write_text(json.dumps(cases,ensure_ascii=False)+'\n')
lines=[]
for c in cases:
 for q in c['queries']:lines.append('\t'.join([str(len(c['fields'])),*[s.encode().hex()for s in c['fields']],q.encode().hex()]))
inputs=('\n'.join(lines)+'\n').encode();(p/'input.hex.tsv').write_bytes(inputs)
java=Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin')
(p/'LookupProbe.java').write_text('''import java.io.*;import java.util.*;import java.nio.charset.StandardCharsets;import org.apache.spark.sql.types.*;
public class LookupProbe{static String text(String s){return new String(HexFormat.of().parseHex(s),StandardCharsets.UTF_8);}public static void main(String[] args)throws Exception{var reader=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));for(String line;(line=reader.readLine())!=null;){var parts=line.split("\\t",-1);int n=Integer.parseInt(parts[0]);StructType fields=new StructType();for(int i=0;i<n;i++)fields=fields.add(text(parts[i+1]),DataTypes.IntegerType,true);var query=text(parts[n+1]);var a=fields.getFieldIndex(query);var b=fields.getFieldIndexCaseInsensitive(query);System.out.println((a.isDefined()?a.get():-1)+","+(b.isDefined()?b.get():-1));}}}
''')
jars=sorted(Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars').glob('*.jar'));cp=os.pathsep.join(map(str,jars))
commands=[['cargo','+1.98.1','build','--offline','--manifest-path',str(p/'Cargo.toml')],[str(java/'javac'),'-cp',cp,str(p/'LookupProbe.java')]]
for i,cmd in enumerate(commands):
 with(p/f'build-{i}.log').open('w')as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
outputs=[]
for name,cmd in [('rust',[str(p/'target/debug/c4-independent-probe')]),('java',[str(java/'java'),'-cp',str(p)+os.pathsep+cp,'LookupProbe'])]:
 commands.append(cmd);r=subprocess.run(cmd,input=inputs,capture_output=True,check=True);(p/(name+'.stdout')).write_bytes(r.stdout);(p/(name+'.stderr')).write_bytes(r.stderr);outputs.append(r.stdout.decode().splitlines());assert len(outputs[-1])==len(lines)
mismatch=[{'line':i,'rust':a,'java':b}for i,(a,b)in enumerate(zip(*outputs))if a!=b]
# The offered source fixture's expectations are also checked against the fresh JVM.
expected=[str(q['exact'])+','+str(q['insensitive'])for c in json.loads(fixture)['cases']for q in c['queries']]
assert outputs[1][:len(expected)]==expected
receipt={'recorded_at':datetime.now(timezone.utc).isoformat(),'commit':subprocess.check_output(['git','-C',repo,'rev-parse',commit],text=True).strip(),'scope':'Exact offered lookup/helper sources in an isolated crate versus fresh Spark StructType helpers; bounded fixtures, no CDC reachability or complete Unicode-context claim','schemas':len(cases),'queries':len(lines),'offered_queries':len(expected),'mismatches':mismatch,'commands':commands,'sources':[{'path':path,'archived':dest,'sha256':hashlib.sha256((p/dest).read_bytes()).hexdigest()}for dest,path in paths.items()],'jars':[{'path':str(j),'sha256':hashlib.sha256(j.read_bytes()).hexdigest()}for j in jars]}
(p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'schemas':len(cases),'queries':len(lines),'mismatches':mismatch[:10],'mismatch_count':len(mismatch)}))
