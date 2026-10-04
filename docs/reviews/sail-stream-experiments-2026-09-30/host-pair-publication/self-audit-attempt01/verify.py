"""Verify the inert publication package locally; never execute embedded scripts."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path,PurePosixPath

EXEMPT={'manifest.json','self-audit.json','FREEZE.json'}
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def regular(root,name):
 rel=PurePosixPath(name)
 if not rel.parts or rel.is_absolute() or '..' in rel.parts or str(rel)!=name or '\\' in name:raise ValueError('unsafe package path')
 p=root.joinpath(*rel.parts)
 if p.is_symlink() or not p.is_file() or any(q.is_symlink() for q in p.parents if q!=root.parent):raise ValueError('nonregular package input')
 return p

def verify(root):
 root=root.resolve();manifest_path=root/'manifest.json';before=pin(manifest_path);m=json.loads(manifest_path.read_bytes())
 actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
 if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('package symlink')
 if actual-EXEMPT != set(m['files']):raise ValueError('package inventory differs')
 for name,expected in m['files'].items():
  if pin(regular(root,name))!=expected:raise ValueError('package bytes differ: '+name)
 for name,expected in m['tracked_relative_dependencies'].items():
  p=(root/name).resolve()
  if not p.is_file() or pin(p)!=expected['fingerprint']:raise ValueError('tracked dependency missing or changed: '+name)
 # Verify sealed bundle is complete, including all historically repeated source bytes.
 copied=json.loads((root/'copy-receipt.json').read_bytes());sealed=root/'sealed-physical-bundle'
 for name,record in copied['copies'].items():
  if pin(regular(root,name))!=record['fingerprint']:raise ValueError('copied bytes differ')
 inventory={str(p.relative_to(sealed)):pin(p) for p in sealed.rglob('*') if p.is_file()}
 if inventory!=copied['sealed_bundle_complete_inventory']:raise ValueError('sealed bundle incomplete')
 requests=json.loads((sealed/'pair-requests.json').read_bytes())
 if requests['plan_sha256']!=m['plan_sha256'] or len(requests['cells'])!=6:raise ValueError('pair request identity differs')
 for cell in requests['cells']:
  qpath=regular(sealed,cell['request'])
  if pin(qpath)['sha256']!=cell['request_sha256']:raise ValueError('request hash differs')
  q=json.loads(qpath.read_bytes())
  if {p.name for p in qpath.parent.iterdir()}!=set(q['files'])|{'request.json'}:raise ValueError('sealed cell inventory differs')
  for name,expected in q['files'].items():
   if pin(regular(qpath.parent,name))!=expected:raise ValueError('sealed input hash differs')
 # Archived metadata references absolute source paths; current README links are local.
 links=[];json_count=0
 for name in m['files']:
  p=root/name
  if p.suffix=='.json':json.loads(p.read_bytes());json_count+=1
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
    target=target.split('#')[0]
    if not target or '://' in target:continue
    t=(p.parent/target).resolve()
    if not t.exists():raise ValueError('broken Markdown link: '+name+' '+target)
    if not t.is_relative_to(root) and str(t) not in {str((root/x).resolve()) for x in m['tracked_relative_dependencies']}:raise ValueError('unlisted external link')
    links.append({'file':name,'target':target})
 patterns={
 'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 'aws_key':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'github_token':re.compile(rb'\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
 'openai_style_token':re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
 'authorization':re.compile(rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}')}
 hits={};text_count=0
 for name in m['files']:
  raw=(root/name).read_bytes();raw.decode('utf-8');text_count+=1
  counts={label:len(p.findall(raw)) for label,p in patterns.items() if p.search(raw)}
  if counts:hits[name]=counts
 if hits:raise ValueError('credential-pattern matches need review; values withheld')
 if pin(manifest_path)!=before:raise ValueError('manifest changed during verification')
 for name,expected in m['files'].items():
  if pin(regular(root,name))!=expected:raise ValueError('package changed during verification')
 return dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_PORTABLE_PACKAGE_HASH_JSON_LINK_AND_BUNDLE_CHECKS',manifest=before,helper=pin(Path(__file__)),files=len(m['files']),bytes=sum(p['bytes'] for p in m['files'].values()),json_files=json_count,local_links=links,credential_scan=dict(utf8_files=text_count,families=list(patterns),matches=hits,scope='Explicit-pattern check; not exhaustive absence of sensitive information.'),limits=['No runtime, result-Parquet read, graph certificate recomputation or remote operation.','Original absolute operational paths are preserved historical metadata; portable evidence does not authorize relaunch.','The package belongs beside its hash-pinned already-tracked Grust dependencies.'])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--receipt',type=Path);a=p.parse_args();r=verify(a.root)
 if a.receipt:
  with a.receipt.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r,indent=2))
if __name__=='__main__':main()
