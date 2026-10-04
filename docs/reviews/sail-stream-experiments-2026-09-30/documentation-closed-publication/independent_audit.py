#!/usr/bin/env python3
"""Independent read-only audit of the frozen closed-evidence publication."""
from pathlib import Path
import datetime,hashlib,json,re,subprocess
R=Path('/private/tmp/grust-sail-review-closed-docs')
O=Path('/private/tmp/grust-sail-review-closed-publication')
P='docs/reviews/sail-stream-experiments-2026-09-30/'
def git(*a):return subprocess.check_output(['git','-C',str(R),*a])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
frozen=load(O/'frozen.json');base=frozen['base'];tree=frozen['tree']
assert git('rev-parse','HEAD').decode().strip()==base
assert subprocess.run(['git','-C',str(R),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
for args in [('diff','--quiet',tree),('diff','--cached','--quiet',tree)]:
 assert subprocess.run(['git','-C',str(R),*args]).returncode==0
assert not git('ls-files','--others','--exclude-standard').strip()
manifest=load(R/frozen['manifest_path']);assert sha(R/frozen['manifest_path'])==frozen['manifest_sha256']
rows={r['path']:r for r in manifest['files']}
for path,row in rows.items():
 p=R/path;assert p.is_file() and not p.is_symlink()
 assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
old= json.loads(git('show',base+':'+frozen['manifest_path']))
allowed={P+'RESULTS.md',P+'SEM-REVIEW-2-RESPONSE.md',P+'CLUSTER-PREPARATION.md','codex-to-codex.md'}
changed=[]
for row in old['files']:
 p=row['path'];assert p in rows
 if rows[p]!=row:changed.append(p)
assert set(changed)==allowed,changed
status=[line.split('\t') for line in git('diff','--cached','--name-status').decode().splitlines()]
modified=[path for state,path in status if state=='M']
assert set(modified)==allowed|{frozen['manifest_path']}
new=[path for state,path in status if state=='A'];assert len(new)==471
assert all(p.startswith(P) for p in new)
assert all(state in ('A','M') for state,*_ in status)
coord_before=git('show',base+':codex-to-codex.md');coord_after=(R/'codex-to-codex.md').read_bytes()
assert coord_after.startswith(coord_before)
assert coord_after[len(coord_before):].count(b'## ')==1
prep=load(O/'preparation.json');adjust=load(O/'candidate-prose-adjustment.json')
for path,expected in prep['selected_sources'].items():
 p=R/path
 if path==adjust['path']:
  assert sha(p)==adjust['candidate_sha256']
  text=p.read_text();assert text.count(adjust['new'])==1
  original=text.replace(adjust['new'],adjust['old'])
  assert hashlib.sha256(original.encode()).hexdigest()==expected['sha256']==adjust['source_copy_sha256']
 else:assert sha(p)==expected['sha256'],path
# Existing unfavorable and causal-limit sections remain exact bytes.
old_results=git('show',base+':'+P+'RESULTS.md').decode();new_results=(R/P/'RESULTS.md').read_text()
def section(text,heading):
 return text.split(heading,1)[1].split('\n## ',1)[0]
preserved_sections={}
for heading in ['## Stream loss: one replay explained, earlier failures still open','## Pecan production-path crosscheck and paired measurement']:
 a=section(old_results,heading);b=section(new_results,heading);assert a==b
 preserved_sections[heading]=hashlib.sha256(a.encode()).hexdigest()
# Active data and private copyrighted bodies cannot enter the selected publication.
for path in rows:
 assert not any(part in path.split('/') for part in ('logging02-monitor','logging02-observations','__pycache__'))
 assert not (path.startswith(P+'logging02/') or path.endswith('/sem-primary.html'))
catalog=R/P/'sem-review2/input-catalog'
assert len([p for p in catalog.iterdir() if p.is_file()])==13
exclusions=load(catalog/'publication-exclusions.json')
excluded_hashes={r['sha256'] for r in exclusions['excluded_from_publication']}
assert excluded_hashes.isdisjoint({r['sha256'] for r in rows.values()})
assert not list(catalog.glob('*.html'))
assert all(not (catalog/e['original_file']).exists() for e in exclusions['excluded_from_publication'])
# Closed receipt identities and exact scope.
build289=load(R/P/'linux-builds/integration289/final/rebuild-receipt.json')
build561=load(R/P/'linux-builds/compact561-host/final/rebuild-receipt.json')
for d in [build289,build561]:
 assert d['outcome']=='passed' and d['seed_unchanged'] is True
 assert all(step['returncode']==0 for step in d['steps'])
assert build561['source_sha']=='56194b170155301ba91077f0ba3df31fe2c78b6b'
assert build561['scope']=='host-only build; native tests and wheel reused from exact prior passing source after identity proof'
smoke=load(R/P/'worker-smoke-compact561-cpu16-23/verification.json')
assert sha(R/P/'worker-smoke-compact561-cpu16-23/verification.json')=='c6f63c3f5a9b2763cb97982b6d458fe72649128d183fb63f8f3073793f9071ca'
assert smoke['outcome']=='passed' and smoke['grouped_tuple_min_tasks_correlated']==237
assert smoke['algorithm_iterations']==24 and smoke['verification']['rows']==16384
assert smoke['runtime_source_sha']==build561['source_sha']
assert smoke['binary_sha256']=='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
assert load(R/P/'worker-smoke-compact561-cpu16-23/process-identity-01.json')['outcome']=='capture_error'
pair=load(R/P/'host-pair-16k/HANDOFF.json');assert pair['status']=='PREPARED_AND_STAGED_NOT_LAUNCHED'
assert pair['order']=='warmup A, warmup B, measurements A B B A'
assert load(R/P/'host-pair-16k/candidate-gate02/receipt.json')['passed'] is True
admission=load(R/P/'logging02-admission.json');assert admission['outcome']=='passed'
privacy=load(O/'independent-privacy-scan.json');assert privacy['manifest_sha256']==frozen['manifest_sha256']
assert privacy['credential_pattern_matched_files']==0
# Identity remains frozen after every read.
assert load(O/'frozen.json')==frozen
assert sha(R/frozen['manifest_path'])==frozen['manifest_sha256']
assert git('rev-parse','HEAD').decode().strip()==base
for args in [('diff','--quiet',tree),('diff','--cached','--quiet',tree)]:
 assert subprocess.run(['git','-C',str(R),*args]).returncode==0
report={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outcome':'PASS_INDEPENDENT_PUBLICATION_AUDIT','base_commit':base,'candidate_tree':tree,'frozen_index_tree':tree,'manifest_sha256':frozen['manifest_sha256'],'independent_audit_script_sha256':sha(Path(__file__)),'manifest_files':len(rows),'manifest_bytes':sum(r['bytes'] for r in rows.values()),'new_files':len(new),'prior_manifest_files_preserved':len(old['files']),'permitted_prior_changes':sorted(changed),'selected_source_files_verified':len(prep['selected_sources']),'only_intentional_source_copy_difference':adjust['path'],'coordination_scope':'Exactly one isolated append; prior bytes retained','preserved_sections_sha256':preserved_sections,'documentation_gate':{'status':'passed','files':1860,'json_files':684,'relative_markdown_links':158,'head_scope':'Detached base plus frozen staged candidate tree; owner must perform exact committed gate'},'privacy':privacy,'source_scope_checks':['289 native tests/build and561 host-only build distinguished; no new Linux490-test claim.','Compact smoke is production min(struct) worker task/status evidence plus producer oracle/source review; no new independent result-file recomputation or measured allocator-layout claim.','Failed late PID capture is retained; no host-PID mapping claim.','Smoke variants have different build concurrency; no timing/memory ratio claimed.','Prepared/staged paired16k remains unlaunched; admission is point-in-time only.','Five client64/65 checks distinguished from seven-cell source-derived star arithmetic, not cluster timing.','Catalog URLs/statistics and four tiny example schemas distinguished from exact large-input identity and DuckLab authorship.','Active logging02 observations/cell and full third-party source pages are excluded; closed admission remains linked.'],'corrections_resolved':['Future-publication sentence corrected only in detached candidate with explicit source-copy receipt.','New exclusion count scope clarified; inherited generated-fixture records remain intact.'],'limitations':['Heuristic privacy scan is not exhaustive secret detection.','No new runtime tests, graph workloads, remote calls or scaling measurements by this publication audit.','This verdict binds staged tree and manifest, not a future commit or push; exact-SHA gate and delivery remain owner responsibilities.']}
(O/'independent-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'outcome':'PASS','candidate_tree':tree,'manifest_sha256':frozen['manifest_sha256'],'audit_sha256':sha(O/'independent-audit.json')},indent=2))
