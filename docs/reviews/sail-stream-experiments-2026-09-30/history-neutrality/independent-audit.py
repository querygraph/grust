from pathlib import Path
from collections import Counter
import subprocess,json,hashlib,datetime,sys
receipt=Path(sys.argv[1]); output=Path(sys.argv[2]); r=json.loads(receipt.read_bytes()); repo=r['private_repository']
def git(*args): return subprocess.check_output(['git','--git-dir='+repo,*args])
def sha(data): return hashlib.sha256(data).hexdigest()
def commit(h):
 headers,msg=git('cat-file','commit',h).split(b'\n\n',1)
 return headers.split(b'\n'),msg

def tree(h):
 entries={}
 for entry in git('ls-tree','-rz','--full-tree',h).split(b'\0'):
  if entry:
   meta,path=entry.split(b'\t',1); entries[path.decode()]=meta.decode()
 return entries

def blob(h,path): return git('show',h+':'+path)
rows=r['commits']; mapping={x['old']:x['new'] for x in rows}; base=r['base_unchanged']; assert len(rows)==16
assert git('rev-list','--reverse',base+'..'+r['old_head']).decode().splitlines()==list(mapping)
assert git('rev-list','--reverse',base+'..'+r['new_head']).decode().splitlines()==list(mapping.values())
allow={'docs/reviews/gn-capacity-2026-09-29.md','docs/SEM-REVIEW-2.md'}; checks=[]
for i,row in enumerate(rows):
 old,new=row['old'],row['new']; oh,om=commit(old);nh,nm=commit(new)
 assert om==nm,('message',old)
 keep=lambda hs:[h for h in hs if not h.startswith((b'tree ',b'parent '))]
 assert keep(oh)==keep(nh),('metadata',old)
 op=[h[7:].decode() for h in oh if h.startswith(b'parent ')]; np=[h[7:].decode() for h in nh if h.startswith(b'parent ')]
 assert len(op)==len(np)==1
 assert op==[base if i==0 else rows[i-1]['old']]
 assert np==[base if i==0 else rows[i-1]['new']]==[row['new_parent']]
 ot,nt=tree(old),tree(new); assert set(ot)==set(nt)
 changed=sorted(k for k in ot if ot[k]!=nt[k]); assert changed==sorted(x['path'] for x in row['changes']); assert set(changed)<=allow
 for path in changed:
  assert ot[path].split()[:2]==nt[path].split()[:2]
  before,after=blob(old,path),blob(new,path); rec=next(x for x in row['changes'] if x['path']==path)
  assert sha(before)==rec['before_sha256'] and sha(after)==rec['after_sha256']
  if path.endswith('gn-capacity-2026-09-29.md'):
   assert [l for l in before.splitlines() if l.startswith(b'|')]==[l for l in after.splitlines() if l.startswith(b'|')]
   old_text=b'That is\nthe number the distributed path has to beat by adding hosts, and the S1/S3\nprojection work applies to Argentea\'s adjacency build as much as to\nBanda\'s.'
   new_text=b'A distributed placement experiment should hold the workload, protocol and\nresource envelope fixed and measure time and memory as resources are added.\nThe S1/S3 projection work applies to Argentea\'s adjacency build as much as\nto Banda\'s.'
   assert before.count(old_text)==1
   assert before.replace(old_text,new_text)==after,('capacity unexpected prose',old)
  else:
   assert i==15
   pre=b'Translated from his messages of 2026-09-30:\n';end=b'His results ('
   quote=lambda b:b.split(pre,1)[1].split(end,1)[0]; assert quote(before)==quote(after)
   start=b'His results (';finish=b'## 3. Where the time goes'
   block=lambda b:b.split(start,1)[1].split(finish,1)[0]; assert block(before)==block(after)
   permitted_deleted={b'| Outcome | Reading | Next |',b'|---|---|---|',b'| L at most 3 | the controller is already in class in one process; the campaign\'s gap is cluster execution | Stage C first |',b'| L between 3 and 20 | both matter | Stage B, then C |',b'| L above 20 | the client-driven loop is the problem whatever the mode | Stage B at once, and open Stage E\'s question now |',b'| Input | Kernel | Sem\'s machine | Target for Sail (3 times, 2 times RSS) |'}
   removed=Counter(l for l in before.splitlines() if l.startswith(b'|'))-Counter(l for l in after.splitlines() if l.startswith(b'|'))
   assert set(removed)<=permitted_deleted,(removed,old)
 checks.append({'old':old,'new':new,'changed_paths':changed,'full_tree_entries':len(ot),'metadata_message_parent_topology':'PASS','blob_hashes':'PASS','evidence_preservation':'PASS'})
assert git('rev-parse','refs/heads/work/neutral-review-candidate').decode().strip()==r['new_head']
v1=json.loads(receipt.with_name('prepared-v1-receipt.json').read_bytes())
assert rows[:15]==v1['commits'][:15]
assert git('diff','--name-only',v1['new_head'],r['new_head']).decode().splitlines()==['docs/SEM-REVIEW-2.md']
audit={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'auditor':'review_native','repository':repo,'candidate':r['new_head'],'source':r['old_head'],'base':base,'mechanical_verdict':'PASS','checks':checks,'prepared_receipt_sha256':sha(receipt.read_bytes()),'audit_script_sha256':sha(Path(__file__).read_bytes()),'all_16_metadata_messages_parent_topology_preserved':True,'all_other_tree_entries_preserved':True,'all_capacity_table_rows_preserved':True,'sem_attributed_quotes_and_measurement_sections_preserved':True,'first_15_mappings_identical_to_v1':True,'only_sem_differs_from_v1':True,'scope':'read-only Git inspection; no refs or repository objects written'}
output.write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps({'mechanical_verdict':'PASS','commits':len(checks),'artifact':str(output),'artifact_sha256':sha(output.read_bytes()),'candidate':r['new_head']},indent=2))
