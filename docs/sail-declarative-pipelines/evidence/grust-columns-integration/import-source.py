from pathlib import Path
import subprocess,json,hashlib
root=Path('/Users/alexy/src/sail-pipelines-proposal')
source='71e4a94d910c7afa978eaf1cc98beccb5df92051'
paths=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',source,'vendor/grust-columns'],text=True).splitlines()
assert len(paths)==5
for path in paths:
 p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
 data=subprocess.check_output(['git','-C',str(root),'show',source+':'+path])
 p.write_bytes(data)
manifest=json.loads((root/'vendor/grust-columns/SOURCE.json').read_text())
for name,expected in manifest['files_sha256'].items():
 data=(root/'vendor/grust-columns'/name).read_bytes()
 original=subprocess.check_output(['git','-C','/Users/alexy/src/grust-sdp','show',manifest['commit']+':'+manifest['path']+'/'+name])
 assert data==original and hashlib.sha256(data).hexdigest()==expected
p=root/'Cargo.toml';s=p.read_text();s=s.replace('    "vendor/grust-topology",','    "vendor/grust-topology",\n    "vendor/grust-columns",');p.write_text(s)
p=root/'Cargo.lock';s=p.read_text();marker='[[package]]\nname = "grust-topology"';assert marker in s and 'name = "grust-columns"' not in s;s=s.replace(marker,'[[package]]\nname = "grust-columns"\nversion = "0.1.0"\n\n'+marker);p.write_text(s)
print('PASS exact four-file Grust source identity; no consumer dependency added')
