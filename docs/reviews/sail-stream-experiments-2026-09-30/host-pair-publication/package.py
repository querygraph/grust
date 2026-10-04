from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess,tarfile
E=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30');P=E/'host-pair-publication'
SEALED=Path('/private/tmp/physical-pair-closed-v4-bundle')
STUDY=E/'host-pair-execution/20261001T015353080533Z-collect-files/study'
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def save(p,d):
 with p.open('x') as s:json.dump(d,s,indent=2);s.write('\n')
assert not P.exists();P.mkdir()
copy_map={};excluded=[]
def cp(src,target):
 assert src.is_file() and not src.is_symlink()
 before=pin(src);dst=P/target;dst.parent.mkdir(parents=True,exist_ok=True)
 with src.open('rb') as a,dst.open('xb') as b:shutil.copyfileobj(a,b,1<<20)
 dst.chmod(src.stat().st_mode & 0o777)
 assert before==pin(src)==pin(dst)
 copy_map[target]={'source':str(src),'source_mode':oct(src.stat().st_mode & 0o777),'fingerprint':before}
def tree(src,target,exclude_md=False):
 for f in sorted(src.rglob('*')):
  assert not f.is_symlink()
  if f.is_file():
   if exclude_md and f.suffix=='.md':
    excluded.append({'source':str(f),'fingerprint':pin(f),'reason':'Historical preparatory prose with external relative context; exact code, controls and preparation receipts are copied. Current authored README explains final scope.'})
   else:cp(f,str(Path(target)/f.relative_to(src)))
# Copy sealed package completely, without rewriting absolute operational paths.
tree(SEALED,'sealed-physical-bundle')
# Study raw tar files are redundant with all four retained, verified member files.
for f in sorted(STUDY.rglob('*')):
 assert not f.is_symlink()
 if not f.is_file():continue
 if f.name=='diagnostics.tar':
  members={}
  with tarfile.open(f,'r:') as t:
   for x in t:
    assert x.isfile() and '/' not in x.name and x.name not in members
    with t.extractfile(x) as s:
     h=hashlib.sha256();n=0
     for block in iter(lambda:s.read(1<<20),b''):h.update(block);n+=len(block)
    v={'bytes':n,'sha256':h.hexdigest()};original=f.parent/'diagnostics'/x.name
    assert v==pin(original)
    members[x.name]={'fingerprint':v,'published_path':str(Path('study')/original.relative_to(STUDY))}
  assert set(members)=={'receipt.json','server.log','server-settings.json','memory-samples.jsonl'}
  excluded.append({'source':str(f),'fingerprint':pin(f),'reason':'Redundant tar: every regular member is retained byte-identically. Tar header bytes are not reconstructed; original tar remains at source.','members':members})
 else:cp(f,str(Path('study')/f.relative_to(STUDY)))
# Outer collector archive is another duplicate of the complete local collected tree.
outer=E/'host-pair-execution'
for f in sorted(outer.iterdir()):
 if f.is_dir():continue
 if f.suffix=='.tar':
  members={}
  with tarfile.open(f,'r:') as t:
   for x in t:
    assert not x.issym() and not x.islnk()
    if x.isdir():continue
    assert x.isfile() and '..' not in Path(x.name).parts and not Path(x.name).is_absolute()
    target=outer/(f.stem+'-files')/x.name
    assert target.is_file()
    with t.extractfile(x) as stream:
     h=hashlib.sha256();n=0
     for block in iter(lambda:stream.read(1<<20),b''):h.update(block);n+=len(block)
    v={'bytes':n,'sha256':h.hexdigest()};assert v==pin(target)
    published=str(Path('study')/target.relative_to(STUDY)) if target.is_relative_to(STUDY) else None
    members[x.name]={'fingerprint':v,'published_path':published if target.suffix!='.tar' else None,'retained_source':str(target)}
  excluded.append({'source':str(f),'fingerprint':pin(f),'reason':'Outer transfer tar duplicates the collected study, including its six redundant diagnostic tar files. Original remains at source; member hashes retained.','members':members})
 else:cp(f,str(Path('outer')/f.name))
tree(E/'host-pair-physical-execution','physical-execution')
tree(E/'host-pair-launch-preparation','launch-preparation')
tree(E/'host-pair-closed-review','independent-review')
tree(E/'physical-output-pair-execution-preparation-v4','physical-preparation-v4',True)
tree(E/'physical-output-pair-execution-preparation','prior-physical-preparation-v2',True)
tree(E/'physical-output-pair-execution-preparation-v3','paused-physical-preparation-v3')
cp(Path(__file__),'package.py')
for n,v in copy_map.items():assert pin(Path(v['source']))==v['fingerprint']==pin(P/n)
# This publication changes no shared index or tracked prose. Index identity is recorded, not rewritten.
git=lambda *a:subprocess.check_output(['git','-C',str(E.parents[2]),*a],env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).decode().strip()
save(P/'copy-receipt.json',{'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'BYTE_IDENTICAL_SELECTED_EVIDENCE_COPIED','copies':copy_map,'sealed_bundle_complete_inventory':{str(f.relative_to(SEALED)):pin(f) for f in sorted(SEALED.rglob('*')) if f.is_file()},'exclusions':excluded,'scope':'Local packaging only. Existing studies, archives, prepared requests, source evidence and RESULTS.md unchanged. Original result Parquet files remain on retained remote volume; they were not copied or read for this packaging.','raw_archive_availability':'Excluded archives are retained at the recorded original local source paths; individual diagnostic members are public. This package does not promise reconstruction of byte-identical tar headers.','git_head_observed':git('rev-parse','HEAD')})
print(json.dumps({'files':len(copy_map),'bytes':sum(v['fingerprint']['bytes'] for v in copy_map.values()),'excluded':len(excluded),'path':str(P)}))
