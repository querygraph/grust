from pathlib import Path
import hashlib,json,subprocess
E=Path(__file__).resolve().parent
for f,h in json.loads((E/'MANIFEST.json').read_text()).items():assert hashlib.sha256((E/f).read_bytes()).hexdigest()==h,f
for r in json.loads((E/'source-audit.json').read_text()):
 data=subprocess.check_output(['git','-C',r['repository'],'show',r['commit']+':'+r['path']]);assert hashlib.sha256(data).hexdigest()==r['sha256']
 assert all(marker in data.decode()for marker in r['markers'])
design=E.parent.parent/'CDC-CONTROL-STORE-DESIGN.md'
assert hashlib.sha256(design.read_bytes()).hexdigest()==json.loads((E/'design.json').read_text())['sha256']
print('Verified pinned control-store design sources/artifact; no backend/fencing/recovery qualification claimed')
