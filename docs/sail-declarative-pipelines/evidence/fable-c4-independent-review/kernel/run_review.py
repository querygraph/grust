from pathlib import Path
import subprocess,json,hashlib
p=Path('/tmp/sail-sdp-c4-kernel-review');p.mkdir();repo='/Users/alexy/src/sail-pipelines-proposal';grust='/Users/alexy/src/grust-sdp'
m=json.loads(subprocess.check_output(['git','-C',repo,'show','a495cb02d:vendor/grust-columns/SOURCE.json']))
for path,digest in m['files_sha256'].items():
 data=subprocess.check_output(['git','-C',repo,'show','a495cb02d:vendor/grust-columns/'+path]);upstream=subprocess.check_output(['git','-C',grust,'show',m['commit']+':'+m['path']+'/'+path]);assert data==upstream and hashlib.sha256(data).hexdigest()==digest
 dest=p/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
checks=[]
for name,cmd in [('test',['cargo','+1.98.1','test','--manifest-path',str(p/'Cargo.toml')]),('clippy',['cargo','+1.98.1','clippy','--manifest-path',str(p/'Cargo.toml'),'--all-targets','--locked','--','-D','warnings','-D','clippy::unwrap_used','-D','clippy::expect_used','-D','clippy::panic']),('fmt',['cargo','+nightly','fmt','--manifest-path',str(p/'Cargo.toml'),'--','--check'])]:
 with(p/(name+'.log')).open('w')as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 checks.append({'name':name,'command':cmd,'exit_code':r.returncode});assert r.returncode==0,(p/(name+'.log')).read_text()
(p/'receipt.json').write_text(json.dumps({'scope':'Standalone exact vendored kernel; not full Grust or Sail gate','source':m,'checks':checks},indent=2)+'\n');print('PASS exact four-file vendor match; 16 standalone kernel tests, strict Clippy, formatting')
