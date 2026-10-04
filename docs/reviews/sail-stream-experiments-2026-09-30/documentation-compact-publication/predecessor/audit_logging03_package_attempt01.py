from pathlib import Path
import hashlib,json,gzip,tarfile,re
from datetime import datetime,timezone
P=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30')
B=P/'logging03-publication'
def fp(p):
 h=hashlib.sha256()
 with p.open('rb') as s:
  for block in iter(lambda:s.read(1<<20),b''):h.update(block)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
frozen_pin=fp(B/'frozen.json');f=json.loads((B/'frozen.json').read_bytes());m=json.loads((B/'manifest.json').read_bytes())
assert frozen_pin['sha256']=='146f60d1f45bc1dbf407da7d343ef51a4789275dd7e8241a2bff16b173279e73'
assert set(f['files'])=={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file()}-{'frozen.json'}
for name,pin in f['files'].items():assert fp(B/name)==pin,name
for name,pin in m['package_files'].items():assert fp(B/name)==pin,name
for name,pin in m['raw_tree'].items():assert fp(P/'logging03-compact'/name)==pin,name
for name,pin in m['support_sources'].items():assert fp(P/name)==pin==fp(B/'support'/name),name
assert len(m['raw_tree'])==14 and sum(x['bytes'] for x in m['raw_tree'].values())==827378117
h=hashlib.sha256();count=0
with gzip.open(B/'diagnostics.tar.gz','rb') as s:
 for block in iter(lambda:s.read(1<<20),b''):count+=len(block);h.update(block)
assert {'bytes':count,'sha256':h.hexdigest()}==m['raw_tree']['diagnostics.tar']
members={}
with tarfile.open(B/'diagnostics.tar.gz','r:gz') as t:
 for x in t:
  assert x.isfile() and '/' not in x.name and x.name not in members and x.name not in ('.','..')
  dig=hashlib.sha256();size=0
  with t.extractfile(x) as s:
   for block in iter(lambda:s.read(1<<20),b''):size+=len(block);dig.update(block)
  assert x.size==size
  members[x.name]={'bytes':size,'sha256':dig.hexdigest()}
assert members==m['archive_members']
restored=json.loads((B/'rehydration02-receipt.json').read_bytes())
assert restored['outcome']=='EXACT_RAW_COLLECTION_RESTORED' and restored['files']==m['raw_tree'] and restored['manifest']==fp(B/'manifest.json')
control=json.loads((B/'controls02-receipt.json').read_bytes());assert control['returncode']==0 and 'Ran 11 tests' in control['stderr']
for name,pin in control['files'].items():assert fp(B/name)==pin
# Independently resolve all published package Markdown links.
links=[]
for p in B.rglob('*.md'):
 for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  target=target.split('#')[0]
  if not target or '://' in target:continue
  assert (p.parent/target).exists(),(p,target)
  links.append({'file':str(p.relative_to(B)),'target':target})
assert fp(B/'frozen.json')==frozen_pin
for name,pin in f['files'].items():assert fp(B/name)==pin,name
producer=json.loads((P/'logging03-compact/diagnostics/receipt.json').read_bytes())
assert producer['outcome']=='passed' and producer['algorithm_iterations']==60 and producer['algorithm_converged'] is True
assert producer['correctness']=={'rows':16777216,'unique':16777216,'reached':8862601,'certificate':'all-edge inequalities and rooted tight-edge reachability','witness_rounds':22,'relative_edge_tolerance':1e-12,'max_edge_slack':5.558314753696322e-12,'conservative_absolute_distance_error_bound':9.326049224058808e-05,'reference':'distributed certificate; no precomputed reference vector','parent_tree_checked':True}
physical=json.loads((P/'logging03-physical-execution/independent-final-review.json').read_bytes());assert physical['outcome']=='PASS_INDEPENDENT_CLOSED_PHYSICAL_EXECUTION_AUDIT' and not physical['blockers']
assert physical['counts']['unique_ids']==16777216 and physical['counts']['unreachable_rows']==7914615
assert round(35481849856/(1<<30),2)==33.04
pairs=json.loads((P/'sssp-candidate-buffer-reuse/allocation-comparison.json').read_bytes())
assert len(pairs['pairs'])==18
large=[r for r in pairs['pairs'] if r['local_vertices']==65536 and r['mode']!='done']
assert large and all(r['delta']['requested_peak']==-(2<<20) and r['delta']['finish_peak_admitted_delta']==-(2<<20) and r['delta']['bytes']==-2097144 for r in large)
exact=json.loads((P/'sssp-candidate-buffer-reuse/exact-gate/receipt.json').read_bytes())
assert exact['outcome']=='PASS' and exact['head']=='fc094a0c25a49edeac2f9f0195aa973421a21a43'
delivery=json.loads((P/'sssp-candidate-buffer-reuse-delivery.json').read_bytes())
assert delivery['outcome']=='PUSHED_AND_REMOTELY_VERIFIED' and set(delivery['remote_after'].values())=={exact['head']}
receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'PASS_INDEPENDENT_LOGGING03_PACKAGE_AND_CLOSED_PROSE_REVIEW','frozen_package':frozen_pin,'manifest':fp(B/'manifest.json'),'reviewed_prose':{n:fp(P/n) for n in ['COMPACT-REPLAY-AND-SSSP.md','RESULTS.md']},'reviewed_helpers':{n:fp(B/n) for n in ['rehydrate.py','package.py','test_rehydrate.py']},'evidence_pins':{n:fp(P/n) for n in ['logging03-compact/diagnostics/receipt.json','logging03-closed-review/receipt.json','logging03-physical-execution/independent-final-review.json','logging03-physical-execution/attempt03/evidence/physical-output.json','logging03-physical-execution/attempt03/evidence/outer-receipt.json','sssp-candidate-buffer-reuse/allocation-comparison.json','sssp-candidate-buffer-reuse/exact-gate/receipt.json','sssp-candidate-buffer-reuse-delivery.json']},'checks':{'frozen_file_count':len(f['files']),'raw_tree_file_count':len(m['raw_tree']),'raw_tree_bytes':827378117,'gzip_decoded_bytes':count,'archive_regular_members':len(members),'support_copies_exact':len(m['support_sources']),'markdown_links_resolved':len(links),'recorded_final_helper_controls':11,'recorded_actual_restoration':'14 original files byte-identical; independently rehashed original raw tree and streamed gzip/archive members; no second destination written'},'blockers':[],'limits':['Local source, hashes and closed recorded outcomes only; no remote access or result-Parquet scan.','Restoration is trusted immutable-evidence restoration, not an adversarial concurrent-filesystem sandbox.','Package historical closed-review prose retains its pre-physical-scan cutoff; new replay document explicitly supplies later physical qualification.','Earlier RESULTS prepared-only paragraph belongs to the historical closed evidence section; latest appended section supplies closure, with no rewriting of prior cutoff.','Producer tolerance-based certificate, supplemental finite/domain physical scan and independent local Argentea component tests remain separate; no Dijkstra, full exact-vector, timing ratio, Linux combined-wheel or scaling verdict added.'],'audit_source':fp(Path(__file__))}
out=Path('/private/tmp/logging03-publication-independent-review.json')
with out.open('x') as s:json.dump(receipt,s,indent=2);s.write('\n')
print(json.dumps({'outcome':receipt['outcome'],'receipt':str(out),'receipt_pin':fp(out),'prose':receipt['reviewed_prose']}))
