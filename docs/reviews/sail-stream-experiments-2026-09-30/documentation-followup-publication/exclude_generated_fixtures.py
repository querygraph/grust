from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess
D=Path('/private/tmp/grust-sail-review-followup-docs');S=Path('/Users/alexy/src/grust');O=Path('/private/tmp/grust-sail-review-followup-publication');R=Path('docs/reviews/sail-stream-experiments-2026-09-30')
M=D/R/'DOCUMENTATION-SNAPSHOT.json';m=json.loads(M.read_text());p=D/R/'wcc-outcome-audit/hardened-c8';excluded=[];dirs=[]
for x in sorted(p.iterdir()):
 if x.is_dir():
  assert x.name.startswith(('matched-resume-','resume-'))
  files=[]
  for f in sorted(x.rglob('*')):
   if not f.is_file():continue
   r=f.relative_to(D);data=f.read_bytes();assert data==(S/r).read_bytes();excluded.append(str(r));files.append({'path':str(r),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
  dirs.append({'path':str(x.relative_to(D)),'purpose':'Generated mock-matrix resume test inputs and scratch outputs; invalid_json cases deliberately contain malformed receipt bytes. No engine execution artifacts.','retained_location':str(S/x.relative_to(D)),'reproducer':str(R/'wcc-outcome-audit/hardened-c8'/('audit.py' if x.name.startswith('matched-') else 'audit-attempt01.py')),'captured_outcome_receipt':str(x.relative_to(D))+'.json','files':files})
  shutil.rmtree(x)
m['files']=[r for r in m['files'] if r['path'] not in excluded]
m['recorded_utc']=datetime.now(timezone.utc).isoformat();m['excluded_file_count']+=len(excluded)
m['generated_fixture_exclusions']=dirs
m['generated_fixture_exclusion_policy']='Only generated local test fixtures/scratch outputs are excluded. Their source files remain intact in shared evidence, including deliberately malformed bytes. Top-level scripts, exact source identities, attempt/final audit receipts and all captured outcome result JSON remain published; these exclusions remove no observed engine failures.'
M.write_text(json.dumps(m,indent=2)+'\n')
(O/'generated-fixture-exclusions.json').write_text(json.dumps({'recorded_utc':datetime.now(timezone.utc).isoformat(),'removed_only_from_isolated_snapshot':dirs,'retained_preliminary_failure':'preliminary-gate.log'},indent=2)+'\n')
subprocess.run(['git','-C',str(D),'add','-A'],check=True)
tree=subprocess.check_output(['git','-C',str(D),'write-tree'],text=True).strip()
frozen={'base':m['base_commit'],'tree':tree,'manifest_path':str(R/'DOCUMENTATION-SNAPSHOT.json'),'manifest_sha256':hashlib.sha256(M.read_bytes()).hexdigest(),'files':len(m['files']),'excluded_generated_files':m['excluded_file_count']}
(O/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n');print(json.dumps(frozen,indent=2))
