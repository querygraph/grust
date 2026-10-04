from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess

SRC=Path('/Users/alexy/src/grust')
DST=Path('/private/tmp/grust-sail-review-followup-docs')
OUT=Path('/private/tmp/grust-sail-review-followup-publication')
REL=Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE='51644023a02185679527304682ed41055ae1c4aa'
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def info(p):return {'sha256':sha(p),'bytes':p.stat().st_size,'mode':oct(p.stat().st_mode & 0o777)}
assert git(DST,'rev-parse','HEAD')==BASE
assert git(DST,'status','--porcelain')==''
index=Path(git(SRC,'rev-parse','--path-format=absolute','--git-path','index'))
shared={'head':git(SRC,'rev-parse','HEAD'),'index':info(index),'coordination':info(SRC/'codex-to-codex.md')}
directories=['followup-union','wcc-certificate','wcc-inbox','wcc-outcome-audit/hardened-c8','pecan-checkpoint-repartition','wcc-fused-worker-plan','linux-builds/integration289/final','worker-smoke-instrumented289-cpu16-23']
files=['DOCUMENTATION-DELIVERY.json','capture_process_identity.py','process-identity-control561.json','process-identity-independent-audit.json','process-identity-staging.json','worker-smoke-289-live-cgroup.json','worker-smoke-289-preflight-extra.json','worker-smoke-instrumented289-cpu16-23.json','worker-smoke-compact561-cpu16-23.json','worker-smoke-cpu16-23-preparation.json','RESULTS.md','SEM-REVIEW-2-RESPONSE.md','min-by-probe/README.md','history-neutrality/independent-extended-audit.py','min-by-probe/run_probe.py','pecan_gate3_cell.py','run_grenada_gate3.py','run_pecan64k_gate3.py','run_pecan_gate3.py','wcc-outcome-audit/reproduce.py']
exclude_parts={'__pycache__','.pytest_cache','pytest-temp','unit-temp','sql-temp'}
selected={REL/x for x in files};excluded=[]
for d in directories:
 for p in (SRC/REL/d).rglob('*'):
  if not p.is_file():continue
  assert not p.is_symlink(),str(p)
  r=p.relative_to(SRC)
  if exclude_parts.intersection(r.parts) or p.suffix=='.pyc':excluded.append(str(r));continue
  selected.add(r)
before={str(p):info(SRC/p) for p in sorted(selected)}
old=json.loads((DST/REL/'DOCUMENTATION-SNAPSHOT.json').read_text())
for r in sorted(selected):
 p=DST/r;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SRC/r,p)
assert before=={str(p):info(SRC/p) for p in sorted(selected)},'selected shared source changed while copying'
assert before=={str(p):info(DST/p) for p in sorted(selected)},'copied bytes or modes differ'
now=datetime.now(timezone.utc).isoformat()
with (DST/'codex-to-codex.md').open('a') as f:
 f.write(f'\n\n## {now} — Codex: ACK completed Sail review evidence publication\n\nRepository `querygraph/grust`: freeze completed WCC outcome and inbox gates, Pecan checkpoint controls, the exact follow-up fork union, and the completed instrumented Linux worker evidence in an isolated detached checkout from `{BASE}`. Preserve prior measurements and failure receipts; exclude the active compact runtime build, newer orchestration/cleanup records and generated fixtures. Publish only after the documentation hash/link/privacy gate and independent audit; this publication carries no new runtime or performance verdict. The shared working files and index are not publication inputs except the explicitly selected completed evidence and three revised review documents.\n')
paths={Path(x['path']) for x in old['files']}|selected|{Path('codex-to-codex.md')}
mutable={REL/'RESULTS.md',REL/'SEM-REVIEW-2-RESPONSE.md',REL/'min-by-probe/README.md',Path('codex-to-codex.md')}
for row in old['files']:
 r=Path(row['path'])
 if r not in mutable:assert sha(DST/r)==row['sha256'],f'prior snapshot altered: {r}'
rows=[{'path':str(r),'sha256':sha(DST/r),'bytes':(DST/r).stat().st_size} for r in sorted(paths)]
manifest={**old,'recorded_utc':datetime.now(timezone.utc).isoformat(),'base_commit':BASE,'publication_branches':['work/proposal-v5','work/sail-graph-review'],'scope':'Completed follow-up reviews, exact fork gates and bounded worker controls; active compact Linux build and larger replay remain pending. Documentation integrity only; no new runtime gate.','pending_excluded_subtrees':['linux-builds/compact561-host','new orchestration observations beyond the prior tracked snapshot','new host-cache-cleanup preparation/receipts','generated fixtures and Python caches'],'excluded_file_count':len(excluded),'excluded_file_count_scope':'generated/cache files omitted within explicitly selected completed subtrees; active unselected files not enumerated','files':rows,'source_copy_guard':'All explicitly copied source bytes, sizes and modes were checked before and after copying; prior tracked evidence bytes remain unchanged except the three selected prose files and appended isolated coordination entry.'}
write(DST/REL/'DOCUMENTATION-SNAPSHOT.json',manifest)
write(OUT/'preparation.json',{'recorded_utc':datetime.now(timezone.utc).isoformat(),'repository':'querygraph/grust','base_commit':BASE,'worktree':str(DST),'shared_before':shared,'selected_sources':before,'selected_directories':directories,'excluded_generated_files':excluded,'prior_snapshot_files':len(old['files']),'manifest_files':len(rows),'manifest_sha256':sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json'),'shared_after':{'head':git(SRC,'rev-parse','HEAD'),'index':info(index),'coordination':info(SRC/'codex-to-codex.md')},'scope':'Only publication worktree edited; shared files/index unchanged by preparer'})
assert shared['index']==info(index)
assert shared['coordination']==info(SRC/'codex-to-codex.md')
print(json.dumps({'copied_files':len(selected),'manifest_files':len(rows),'excluded_generated_files':len(excluded),'manifest_sha256':sha(DST/REL/'DOCUMENTATION-SNAPSHOT.json')},indent=2))
