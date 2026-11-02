from pathlib import Path
import json,hashlib,re,subprocess,collections
root=Path('/Users/alexy/src/grust-sdp-review-gate');p=root/'FABLE-HANDOFF.md';s=p.read_text();assert 250<len(s.splitlines())<500
assert 'SNAPSHOT_TIMESTAMP' not in s and 'CF-0043' in s and 'CF-0044' in s
head=subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','rev-parse','HEAD'],text=True).strip()
assert head in s
for doc in [p,root/'codex-fable-handoff.md',root/'docs/sail-declarative-pipelines/handoff-tools/README.md']:
 for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
  if not link.startswith(('http:','https:','#','mailto:')):assert (doc.parent/link.split('#')[0]).exists(),(doc,link)
repos=['/Users/alexy/src/sail-pipelines-proposal','/Users/alexy/src/grust-sdp','/Users/alexy/src/spark-sdp-4.2.1','/Users/alexy/src/orc-rust-sdp','/Users/alexy/src/sail-iggy-sdp-review','/Users/alexy/src/iggy','/Users/alexy/src/lakecat-sdp-gate']
for sha in set(re.findall(r'`([0-9a-f]{8,40})`',s)):
 assert any(subprocess.run(['git','-C',repo,'cat-file','-e',sha+'^{commit}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0 for repo in repos),sha
m=json.loads((root/'docs/sail-declarative-pipelines/handoff-tools/SNAPSHOT.json').read_text())
for f in m['files']:
 data=(root/'docs/sail-declarative-pipelines/handoff-tools'/f['path']).read_bytes();assert len(data)==f['bytes'] and hashlib.sha256(data).hexdigest()==f['sha256']
x=json.loads((root/'docs/sail-declarative-pipelines/spark-4.2.1-inventory.json').read_text());assert len(x['cases'])==462 and sum('coverage_review'in c for c in x['cases'])==97
assert dict(collections.Counter(c['status']for c in x['cases']))=={'unmapped':400,'partial-behavioral-port':62}
print('PASS replacement Fable handoff links, commit objects, inventory and durable tool snapshots')
