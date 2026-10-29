"""Counter-schedules for proposed protocols; not tests of deployed backends."""
from datetime import datetime,timezone
from pathlib import Path
import json
cases=[]
# Create-if-absent on a progress key does not atomically consult a separate lease key.
objects={'lease/1':{'owner':'A','epoch':1},'progress/0':{'epoch':1}}
a_checked_epoch=1
objects['lease/2']={'owner':'B','epoch':2}
assert 'progress/1' not in objects
objects['progress/1']={'epoch':a_checked_epoch,'batch':0}
assert objects['progress/1']['epoch'] != objects['lease/2']['epoch']
cases.append({'name':'separate_lease_and_progress_keys','kind':'draft counterexample','observation':'A stale owner publishes progress after B acquired a newer lease; the progress filename was still absent.'})
# A unified head serializes acquisition and progress through the same version slot.
head={'version':0,'epoch':1};expected_a=dict(head)
head={'version':1,'epoch':2}
a_can_publish=head==expected_a
assert not a_can_publish
cases.append({'name':'unified_head_rejects_stale_parent','kind':'amended model invariant','observation':'Lease takeover changes the same head version; A cannot publish against its old expected head.'})
# One-batch-ahead restore is not detected by a rule that rejects only > next batch.
store={'committed_batch':0,'intent':None,'next_offset':0}
sink={'committed_batch':1,'committed_range':[0,10]}
recreated_intent={'batch':1,'range':[0,20]}
naive_confirm=sink['committed_batch']==recreated_intent['batch']
assert naive_confirm and sink['committed_range']!=recreated_intent['range']
cases.append({'name':'one_batch_ahead_without_original_intent','kind':'draft counterexample','observation':'Matching batch numbers hide a different input range after an intent-losing restore; adoption would acknowledge unwritten input.'})
# Distinct generation idempotency keys alone do not reject a stale generation.
accepted_keys=set();rows=[]
accepted_keys.add(('g2',0));rows.append('fresh')
accepted_keys.add(('g1',0));rows.append('stale-after-reset')
assert rows==['fresh','stale-after-reset']
cases.append({'name':'generation_scoped_dedup_is_not_reset_fencing','kind':'capability counterexample','observation':'A sink that deduplicates only by (generation,batch) accepts both generations; separate reset fencing must be proved for each real sink.'})
# Apply Spark's documented merge inequalities to a frozen reconciled source.
aux={};target={}
a={'key':1,'upsert':10,'delete':None} # reconciled before B's tombstone exists
b={'key':1,'upsert':None,'delete':20}
aux[b['key']]=b['delete'] # B aux merge
# B target merge: an absent-key delete does not insert.
assert not target
# A aux merge cannot remove the newer tombstone (10 >= 20 is false).
if a['upsert']>=aux[a['key']]:del aux[a['key']]
# A target merge: absent-key upsert inserts; it does not consult aux again.
target[a['key']]=a['upsert']
assert aux[1]==20 and target[1]==10
cases.append({'name':'independent_flow_leases_shared_cdc_target','kind':'draft counterexample under explicit frozen-source premise','observation':'A reconciles upsert 10; B completes delete 20; A inserts 10 after B. Per-flow leases and per-table atomic merges do not establish target-wide CDC isolation. Not an observed Spark/Sail runtime defect.'})
# A partial CDC commit is not a whole-batch completion certificate.
effects={'auxiliary':True,'target':False}
assert any(effects.values()) and not all(effects.values())
cases.append({'name':'cdc_requires_all_effect_receipts','kind':'amended model invariant','observation':'An auxiliary-only receipt cannot advance the whole CDC batch; confirmation must cover every required durable effect.'})
r={'recorded_at':datetime.now(timezone.utc).isoformat(),'scope':'Executed finite protocol models; no production control store or CDC implementation exists here','cases':cases}
Path('/tmp/sail-sdp-fable-response-models.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
