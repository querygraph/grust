#!/usr/bin/env python3
"""Independent read-only audit of the fourth frozen diagnostic publication."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math,re,subprocess
R=Path('/private/tmp/grust-sail-review-interim2-docs');O=Path('/private/tmp/grust-sail-review-interim2-publication');P='docs/reviews/sail-stream-experiments-2026-09-30/'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
def git(*args):return subprocess.check_output(['git','-C',str(R),*args])
def state(f):
 assert git('rev-parse','HEAD').decode().strip()==f['base']
 assert subprocess.run(['git','-C',str(R),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
 for flags in [[],['--cached']]:assert subprocess.run(['git','-C',str(R),'diff',*flags,'--quiet',f['tree']]).returncode==0
 assert not git('ls-files','--others','--exclude-standard').strip()
f=load(O/'frozen.json');state(f);m=load(R/f['manifest_path']);assert sha(R/f['manifest_path'])==f['manifest_sha256'];rows={x['path']:x for x in m['files']};assert len(rows)==len(m['files'])==1974
for path,row in rows.items():
 p=R/path;assert p.is_file() and not p.is_symlink();assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
old=json.loads(git('show',f['base']+':'+f['manifest_path']));assert len(old['files'])==1860
changed=[]
for row in old['files']:
 assert row['path'] in rows
 if row!=rows[row['path']]:changed.append(row['path'])
assert set(changed)=={P+'RESULTS.md',P+'SEM-REVIEW-2-RESPONSE.md','codex-to-codex.md'}
assert (R/'docs/SEM-REVIEW-2.md').read_bytes()==git('show',f['base']+':docs/SEM-REVIEW-2.md')
status=[line.split('\t') for line in git('diff','--cached','--name-status').decode().splitlines()];assert len(status)==118
assert {path for status,path in status if status=='M'}==(set(changed)-{'docs/SEM-REVIEW-2.md'})|{f['manifest_path']}
assert all(s in ('A','M') for s,p in status);new=[p for s,p in status if s=='A'];assert len(new)==114 and all(p.startswith(P) for p in new)
coord_old=git('show',f['base']+':codex-to-codex.md');coord=(R/'codex-to-codex.md').read_bytes();assert coord.startswith(coord_old);assert coord[len(coord_old):].count(b'## ')==1
prep=load(O/'preparation.json');assert not prep['candidate_only_prose_differences'];assert len(prep['selected_sources'])==116
for path,row in prep['selected_sources'].items():assert sha(R/path)==row['sha256'],path
old_results=git('show',f['base']+':'+P+'RESULTS.md').decode();results=(R/P/'RESULTS.md').read_text();heading='## Instrumented replay: interim observations and limits'
block=results.split(heading,1)[1].split('\n## ',1)[0]
without=results.replace(heading+block+'\n','',1)
followup='The subsequent `7bb00a2` answers have also been reviewed: the input pointer\nand library entry point are identified, while the cross-input isolate claim,\nper-action distributed embedding and wide-index fallback still need the\nqualifications recorded in that response.\n'
assert without.count(followup)==1
without=without.replace(followup,'',1)
assert without.split('\n',3)[3]==old_results.split('\n',3)[3], 'prior RESULTS changed beyond timestamp/interim/7bb note'
assert all(x in block for x in ['20:51:32','63.74','427','72.469','42.082','117,575,606','114,476,972','not measured physical disk traffic','hypotheses, not observed stream causes'])
assert '20:57' not in block and '20:58' not in block
obsdir=R/P/'logging02-monitor';observations=sorted(obsdir.glob('observation-*.json'));assert len(observations)==32
cutoff=datetime.fromisoformat('2026-09-30T20:57:33.709595+00:00');timeouts=[]
for p in observations:
 d=load(p);assert datetime.fromisoformat(d['local_finished_utc'])<=cutoff
 if d.get('error','').startswith('TimeoutExpired'):timeouts.append(p.name)
assert len(timeouts)==8
assert all((obsdir/p).exists() for p in ['observer-loop-stop.json','observer-loop-stop02.json','executable-identity-20260930T201123530215Z.json'])
assert load(obsdir/'executable-identity-20260930T201123530215Z.json')['capture']['returncode']==1
assert not (obsdir/'one-shot-2057-summary.json').exists()
assert not any('ledger' in p.name for p in obsdir.iterdir())
summary=load(obsdir/'one-shot-2051-summary.json');source=obsdir/summary['source'];assert sha(source)==summary['source_sha256'];d=load(source)
assert summary['remote_finished_utc']==d['finished_utc'];assert summary['memory_current_bytes']==int(d['observation']['cgroup']['memory.current'])
assert round(summary['memory_current_bytes']/2**30,2)==63.74
assert not summary['file_offsets']['receipt.json']['exists'];assert summary['sampler_latest']['phase']=='execute';assert summary['error_scan']['matches']==[]
assert summary['memory_events_raw']==d['observation']['cgroup']['memory.events']
assert not d['observation']['files']['receipt.json']['exists']
assert all(int(line.split()[1])==0 for line in summary['memory_events_raw'].splitlines())
# Recompute sparse sampler bounds from its pinned 31 inputs, not the later 20:57 observation.
a=load(R/P/'sampler-observation-audit/receipt.json');samples={};pairs={};occ=0;fragments=0
for item in a['inputs']:
 p=obsdir/item['file'];assert sha(p)==item['sha256'];tail=load(p).get('observation',{}).get('files',{}).get('memory-samples.jsonl',{}).get('tail_utf8','');prev=None
 for line in tail.splitlines(keepends=True):
  if not line.endswith('\n'):fragments+=1;prev=None;continue
  try:v=json.loads(line)
  except json.JSONDecodeError:fragments+=1;prev=None;continue
  start,end=v.get('scan_started_seconds'),v.get('scan_finished_seconds')
  if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (start,end)):prev=None;continue
  occ+=1
  if start in samples:assert samples[start]==v
  samples[start]=v
  if prev is not None:pairs[(prev['scan_started_seconds'],start)]=(start-prev['scan_started_seconds'],start-prev['scan_finished_seconds'])
  prev=v
values=[v['scan_finished_seconds']-v['scan_started_seconds'] for v in samples.values()]
assert len(a['inputs'])==31 and len(samples)==a['unique_complete_rows']==427 and occ==a['complete_row_occurrences']==460
assert fragments==23 and len(pairs)==a['within_tail_neighbor_start_gap_seconds']['count']==407
assert min(values)==a['scan_duration_seconds']['minimum'] and max(values)==a['scan_duration_seconds']['maximum']
assert max(v[0] for v in pairs.values())==a['within_tail_neighbor_start_gap_seconds']['maximum']
assert max(v[1] for v in pairs.values())==a['within_tail_neighbor_previous_finish_to_next_start_seconds']['maximum']
assert all(v>.05 for v in values)
# PING counterproof has a separate fixed 20:41 tail; no peer or runtime is identified.
ping=load(R/P/'scheduler-starvation-source-audit/monitor-ping-audit.json');selected=ping['selected_single_tail'];assert sha(R/selected['path'])==selected['observation_sha256'];tail=load(R/selected['path'])['observation']['files']['server.log']['tail_utf8'];assert hashlib.sha256(tail.encode()).hexdigest()==selected['tail_sha256']
pattern=r'^\[([^ ]+) TRACE h2::proto::ping_pong\] recv PING USER ack$';times=re.findall(pattern,tail,re.M);assert len(times)==selected['received_user_ping_ack_records']==138;assert times[0]==selected['first_ack_timestamp'] and times[-1]==selected['last_ack_timestamp']
assert selected['path'].endswith('observation-20260930T204108056578Z.json');assert ping['outcome']=='CONTRARY_TO_CONTINUOUS_GLOBAL_BLACKOUT_NOT_A_PER_PEER_CONTROL'
for row in ping['snapshot_inventory']:assert sha(R/row['path'])==row['sha256']
static=load(R/P/'scheduler-starvation-source-audit/source-audit.json');assert static['outcome']=='SOURCE_MECHANISM_CONFIRMED_CAUSE_UNDETERMINED';assert static['sail_commit']=='2894a962076d3cc404dd72ec736ebeb9239901f6'
for row in static['sources']:
 p=Path(row['local_path']);assert sha(p)==row['sha256'];lines=p.read_bytes().splitlines(keepends=True)
 for span in row['spans']:assert hashlib.sha256(b''.join(lines[span['first_line']-1:span['last_line']])).hexdigest()==span['sha256']
# Host cumulative swap counts have no conversion to physical disk bytes.
host=load(obsdir/'host-memory-comparison.json')
for path,digest in host['source_sha256'].items():assert sha(obsdir/path)==digest
before_raw=load(obsdir/'host-before.json')['snapshots']['vm_stat']['stdout']
current_raw=load(obsdir/'host-control-20260930T204454196825Z.json')['host']['snapshots']['vm_stat']['stdout']
for key,delta in [('Swapins',117575606),('Swapouts',114476972)]:
 row=host['vm_stat_counters'][key]
 assert int(re.search(r'^'+key+r':\s+(\d+)\.',before_raw,re.M)[1])==row['before_pages_or_count']
 assert int(re.search(r'^'+key+r':\s+(\d+)\.',current_raw,re.M)[1])==row['current_pages_or_count']
 assert row['current_pages_or_count']-row['before_pages_or_count']==row['delta']==delta
 assert set(row)=={'before_pages_or_count','current_pages_or_count','delta'}
row=host['vm_stat_counters']['Pages occupied by compressor'];assert row['before_gib']==row['before_pages_or_count']*4096/2**30;assert row['current_gib']==row['current_pages_or_count']*4096/2**30
assert not any(p.startswith(P+'logging02/') or '__pycache__' in p.split('/') or p.endswith('/sem-primary.html') for p in rows)

# Renewed base preserves Fable's source document exactly; new response qualifies claims.
assert f['expected_remote_refs']=={'refs/heads/work/proposal-v5':'7bb00a299db9a24c35a47022614d6f572309b9a2','refs/heads/work/sail-graph-review':'b478e57cb34220c1f671dca7ce92b2b061867855'}
for commit in f['expected_remote_refs'].values():assert subprocess.run(['git','-C',str(R),'merge-base','--is-ancestor',commit,f['base']]).returncode==0
response=(R/P/'SEM-REVIEW-2-RESPONSE.md').read_text();prior_response=git('show',f['base']+':'+P+'SEM-REVIEW-2-RESPONSE.md').decode()
# Root updated the generated timestamp and appended the new section; earlier review remains.
assert response.split("## Review of Sem's answers at `7bb00a2`")[0].split('\n',3)[3].rstrip()==prior_response.split('\n',3)[3].rstrip()
source_audit=load(R/P/'sem-review2/latest-7bb-source-audit/receipt.json');assert sha(R/P/'sem-review2/latest-7bb-source-audit/receipt.json')=='f479d0ebc7f2232e954b42e72e87611c1632c6e1aa4a47205d051682106e9018'
assert source_audit['external_runtime_source']=='b4da56dabe20bba8e29563e06acc5179b2113ce3' and source_audit['external_results_commit']=='ba2fdd8f51fa7fafdca15012d2741f5f8d80c024'
input_control=load(R/P/'sem-review2/latest-7bb-input-control/receipt.json')
for item in input_control['source_files'].values():assert sha(R/item['path'])==item['sha256']
assert sha(R/P/'sem-review2/latest-7bb-input-control/probe.py')==input_control['probe_sha256']
assert input_control['own_input']['self_loops']==2798 and input_control['own_input']['duplicate_count'] is None and input_control['own_input']['isolated_count'] is None
case=input_control['counterexample'];adj={v:set() for v in case['own_vertices']}
for a,b in case['own_edges_undirected']:adj[a].add(b);adj[b].add(a)
reached={case['own_source']};front=list(reached)
while front:
 for v in adj[front.pop()]:
  if v not in reached:reached.add(v);front.append(v)
assert sorted(reached)==case['own_reached'] and sorted(set(adj)-reached)==case['own_unreached']
assert not [v for v in adj if not adj[v]] and len(reached)/case['other_graph_vertex_count']==case['cross_graph_ratio']==1.0
assert input_control['arithmetic_only']['edge_count_difference']==268435456-260379520==8055936
assert abs(input_control['arithmetic_only']['cross_input_ratio_decimal']-8862601/8870942)<1e-15
stopped=R/P/'documentation-interim-stopped-publication';assert sha(stopped/'independent-audit.json')=='86e446077f3cb7c8985bf44813685a2757921798fd938c329114aa7f0b804e1b'
assert (stopped/'shared-guard-stop.json').exists();assert load(stopped/'frozen.json')['base']=='b478e57cb34220c1f671dca7ce92b2b061867855'

# Existing prior evidence remains unchanged.
privacy=load(O/'independent-privacy-scan.json');assert privacy['credential_pattern_matched_files']==0 and privacy['manifest_sha256']==f['manifest_sha256']
log=(O/'independent-documentation-gate.log').read_text();assert log.endswith('SAIL_REVIEW_DOCUMENTATION PASSED '+f['base']+'\n');gate=json.loads(log[:log.rfind('\nSAIL_REVIEW_DOCUMENTATION')]);assert gate['files']==1974
state(f);assert load(O/'frozen.json')==f and sha(R/f['manifest_path'])==f['manifest_sha256']
receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'PASS_INDEPENDENT_PUBLICATION_AUDIT','base_commit':f['base'],'frozen_index_tree':f['tree'],'manifest_sha256':f['manifest_sha256'],'independent_audit_script_sha256':sha(Path(__file__)),'manifest_files':len(rows),'manifest_bytes':sum(x['bytes'] for x in rows.values()),'prior_manifest_files_retained':1860,'new_files':114,'selected_source_copies_verified':116,'prior_changes_only':changed,'coordination':'One isolated append; all preceding bytes retained.','gate':gate,'privacy':privacy,'claims_checked':['RESULTS adds timestamp/interim section/7bb pointer only; prior failures and unfavorable results preserved.','20:51 prose cutoff remains explicit; later 20:57 completed observation is inventory evidence, not a new prose or whole-run verdict.','All eight observer timeout receipts and both local stop attempts are present; failed executable capture retained.','32 copied observations are complete and no later observation, later summary or live ledger is included.','Sampler recomputed from pinned 31 inputs:427 unique/460 occurrences/23 fragments/407 neighbor pairs; bounded sparse tails only.','PING audit independently uses fixed20:41 tail:138 ACK records; no per-peer/runtime/RTT attribution.','31 static source files/spans rehashed; runtime sharing and cooperation boundaries remain not-a-cause conclusion.','Host Swapins/Swapouts retained as cumulative page counts, not measured physical disk traffic or workload attribution.','63.74GiB/zeroOOM/execute/no receipt and bounded empty error matches agree with20:51 raw observation.','New7bb response source-reviewed: correct WCC/API/join/representation boundaries; 5vertex fixture recomputed, no large-input isolation claim.','Stopped old-base candidate/audit/guard failure preserved without pretending it was published.','No matched timing, whole-run completion, scaling or failure-cause claim.','Prepared logging03 audit remains static; no workload launched by audit/publication.'],'publication_control_review':{'scripts_sha256':{name:sha(O/name) for name in ['guard.py','commit_and_gate.sh','publish.py']},'finding':'No blocker: source/shared-state/audit guards precede candidate gate; commit is in the same conditional && chain, followed by exact-SHA gate. Atomic explicit leases use separate expected refs (proposal7bb, reviewb478), with direct-parent/exact-tree and per-ref ancestry checks proving both fast-forwards. Audit did not execute commit or push.'},'limitations':['Heuristic privacy scan is not exhaustive.','This audit verifies captured evidence and source, not unobserved intervals, actual task progress, a failing peer or complete replay result.','No builds, remote calls, workload or candidate/shared-file edits.','Verdict binds frozen staged tree; owner must condition commit on gates and run exact-SHA verification before publication.']}
(O/'independent-audit.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'outcome':receipt['outcome'],'tree':f['tree'],'audit_sha256':sha(O/'independent-audit.json')}))
