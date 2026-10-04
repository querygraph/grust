"""Read-only local audit of the closed six-cell study and later physical checks."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,math,re,statistics,tarfile
E=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30')
O=E/'host-pair-closed-review';S=E/'host-pair-execution/20261001T015353080533Z-collect-files/study'
B=Path('/private/tmp/physical-pair-closed-v4-bundle');R=E/'host-pair-physical-execution/evidence'
BOOT='f5443bfc-c939-491a-a984-b73cc6d1cb20'
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return dict(bytes=p.stat().st_size,sha256=h.hexdigest())
def sha(p):return pin(p)['sha256']
def load(p):return json.loads(p.read_bytes())
def utc(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def kv(s):return {k:int(v) for k,v in (line.split() for line in s.splitlines())}
def vm(s):return {k.strip('"'):int(v) for k,v in re.findall(r'^(.+?):\s+(\d+)\.',s,re.M)}
def inventory(p):return {str(q):pin(q) for q in sorted(p.rglob('*')) if q.is_file()}
initial={**inventory(S),**inventory(B),**inventory(R)}
planpath=E/'host-pair-16k/pair16k-20260930201356-plan.json';plan=load(planpath)
assert sha(planpath)=='d51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
summary=load(S/'summary.json');seq=load(S/'sequence.json');audit=load(E/'host-pair-execution/collection-audit.json')
assert summary['rows']==seq['rows'] and len(seq['rows'])==6 and summary['unrecorded']==[]
assert seq['plan_sha256']==sha(planpath) and summary['measurement_order']=='ABBA'
assert audit['integrity_status']=='integrity_verified' and audit['ratio_eligible'] and audit['errors']==audit['inconclusive_reasons']==[]
for name,p in audit['evidence_files'].items():assert pin(Path(name))==p,name
pr=load(B/'pair-requests.json');serial=load(R/'serial-receipt.json');allsix=load(B/'all-six-closures.json')
assert sha(B/'pair-requests.json')=='55941c6758529696dc088eec37077cbddd3d1fbf8f4868d182435c04c062c5e4'
assert pr['plan_sha256']==sha(planpath) and pr['pair_audit_sha256']==sha(B/'pair-collected-evidence.json')==sha(E/'host-pair-execution/collection-audit.json')
assert pr['all_six_sha256']==sha(B/'all-six-closures.json') and pr['run_pair_sha256']==sha(B/'run_pair.py')
assert serial['outcome']=='six_checks_closed' and serial['supplemental_physical_qualification'] and serial['errors']==[] and serial['inputs_and_reports_unchanged']
assert serial['original_ratio_eligible'] and len(serial['cells'])==len(pr['cells'])==len(allsix['cells'])==6
prep=load(E/'physical-output-pair-execution-preparation-v4/preparation.json')
source=E/'physical-output-pair-execution-preparation-v4'
assert sha(B/'run_pair.py')==sha(source/'run_pair.py')
rows=[];previous=None;previous_check=None
for run,row,check,pair,allcell in zip(plan['runs'],seq['rows'],serial['cells'],pr['cells'],allsix['cells']):
 i=run['order'];label=f'{i:02}';host=run['host'];runtime=plan['hosts'][host]
 assert all(x['order']==i for x in [row,check,pair,allcell])
 assert row['phase']==check['phase']==run['phase'] and row['host']==check['host']==pair['host']==host
 assert row['outcome']==row['receipt_outcome']=='passed' and row['comparison_eligible'] and row['identity_errors']==[]
 assert row['boot_id']==BOOT and row['runner_returncode']==0 and not row['runner_wall_timeout']
 if previous:assert utc(row['started_utc'])>=utc(previous)
 previous=row['finished_utc']
 c=S/'cells'/Path(run['configuration']).stem;prod=load(c/'diagnostics/receipt.json');orch=load(c/'cell/orchestration.json')
 conf=load(c/'configuration.json');pref=load(S/f'{label}.preflight.json')
 assert sha(c/'configuration.json')==run['configuration_sha256']==sha(E/'host-pair-16k'/run['configuration'])
 expected=dict(plan['expected_arguments'],sail_binary=runtime['binary'],runtime_source_sha=runtime['source'],output=run['cell_output'])
 assert prod['arguments']==expected and prod['dataset']==plan['expected_dataset']
 assert prod['native_package_identity']==plan['expected_native_package_identity']
 assert prod['harness_source_sha']=='3a9028057c6c6c5034492845926fc4bc18f9626f' and prod['source_dirty']==''
 assert prod['runtime_source_sha']==runtime['source'] and prod['binary_sha256']==run['binary_sha256']==runtime['sha256']
 assert prod['native_source_sha']=='ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
 assert prod['outcome']=='passed' and prod['algorithm_iterations']==24 and prod['algorithm_converged']
 assert prod['correctness']=={'rows':16384,'unique':16384,'parent_tree_checked':True,'reference':'independent BFS/heap-Dijkstra'}
 assert prod['cleanup_errors']==[] and prod['staging_files_after_shutdown']==[]
 assert orch==row['orchestration'] and not orch['outer_timeout'] and orch['transport_errors']==[]
 st=orch['inspect']['state'];assert st['Status']=='exited' and st['ExitCode']==0 and not st['OOMKilled'] and orch['remove']['returncode']==0
 limits=orch['inspect']['limits'];assert limits['Memory']==limits['MemorySwap']==12<<30 and limits['NanoCpus']==8000000000 and limits['CpusetCpus']=='16-23'
 assert pref['outcome']=='passed' and pref['config_sha256']==run['configuration_sha256']
 obs=pref['observed'];assert obs['boot_id']==BOOT and obs['binary_sha256']==runtime['sha256'] and obs['harness_status']=='' and obs['harness_head']==prod['harness_source_sha']
 assert obs['datasets']['weighted16k']['sha256']==plan['dataset_manifest_sha256'] and obs['free_bytes']>=plan['minimum_free_bytes']
 for direction in ['before','after']:assert pref['running_'+direction]['returncode']==0 and pref['running_'+direction]['stdout'].strip()==''
 # Independently compare tar payloads with the collected extracted bytes.
 names=set()
 with tarfile.open(c/'diagnostics.tar','r:') as archive:
  for entry in archive:
   assert entry.isfile() and '/' not in entry.name and entry.name not in names
   names.add(entry.name);h=hashlib.sha256();size=0
   with archive.extractfile(entry) as f:
    for block in iter(lambda:f.read(1<<20),b''):size+=len(block);h.update(block)
   assert {'bytes':size,'sha256':h.hexdigest()}==pin(c/'diagnostics'/entry.name)
 assert names=={'server.log','memory-samples.jsonl','receipt.json','server-settings.json'}
 samples=[json.loads(line) for line in (c/'diagnostics/memory-samples.jsonl').read_text().splitlines()]
 assert len(samples)==prod['memory']['samples'] and dict(Counter(x['phase'] for x in samples))==prod['memory']['phase_sample_counts']
 assert prod['memory']['error'] is None and prod['memory']['thread_alive'] is False
 for phase,peaks in prod['memory']['phase_peaks'].items():
  for k,v in peaks.items():assert max(x[k] for x in samples if x['phase']==phase and x[k] is not None)==v
 for key in ['pss','rss']:assert row['execution_'+key+'_bytes']==prod['memory']['phase_peaks']['execute'][key+'_bytes']
 assert row['seconds']==prod['end_to_end_seconds'] and row['guest_steal_fraction']==prod['guest_steal_fraction']==0
 assert row['cgroup_execution_after']==prod['cgroup_execution_after'] and row['cgroup_after']==prod['cgroup_after']
 for stage in ['cgroup_execution_before','cgroup_execution_after','cgroup_after']:
  cg=prod[stage];assert cg['memory.max']==str(12<<30) and cg['memory.swap.max']=='0' and cg['cpu.max']=='800000 100000' and cg['cpuset.cpus.effective']=='16-23'
  assert all(v==0 for v in kv(cg['memory.events']).values())
 cpu0=kv(prod['cgroup_execution_before']['cpu.stat']);cpu1=kv(prod['cgroup_execution_after']['cpu.stat'])
 concurrency=row['concurrency_sampling'];assert concurrency['observed_sibling_containers']==[] and concurrency['inventory_errors']==0
 # The supplemental check is exactly the sealed request for this closed producer.
 qb=B/Path(pair['request']).parent;q=load(qb/'request.json');r=R/label
 assert sha(qb/'request.json')==pair['request_sha256']==check['request_sha256']
 for name,p in q['files'].items():assert pin(qb/name)==p
 for name in ['supervise.py','container_check.py','pair_policy.py']:assert sha(qb/name)==sha(source/name)
 assert sha(qb/'producer-receipt.json')==sha(c/'diagnostics/receipt.json')==allcell['receipt_sha256']
 assert sha(qb/'configuration.json')==run['configuration_sha256'] and sha(qb/'closed-audit.json')==allcell['closure_sha256']
 closed=load(qb/'closed-audit.json');assert closed['integrity_status']=='integrity_verified' and closed['errors']==[] and closed['inconclusive_reasons']==[]
 for name,p in closed['files'].items():assert pin(Path(name))==p
 outer=load(r/'outer-receipt.json');inner=load(r/'physical-output.json');ad=load(r/'reader-admission.json');ex=load(r/'exited-container.json')
 assert check['outer_receipt_sha256']==sha(r/'outer-receipt.json') and check['physical_report']==pin(r/'physical-output.json')
 assert outer['request_sha256']==pair['request_sha256'] and outer['bundle_unchanged'] and outer['errors']==[]
 assert outer['supervisor_sha256']==q['files']['supervise.py']['sha256'] and outer['outcome']=='container_completed' and outer['cleanup']=='removed_after_state_capture'
 assert outer['container_id']==ex['Id'] and ex['State']==outer['container_state']==check['container_state']
 st=ex['State'];assert st['Status']=='exited' and st['ExitCode']==0 and st['OOMKilled'] is False and st['Running'] is False and st['Error']==''
 assert ex['Labels']['physical-check.request']==pair['request_sha256'] and ex['Labels']['physical-check.execution']==outer['execution_id']
 assert ex['User']=='0:20' and ex['Memory']==ex['MemorySwap']==2<<30 and ex['NanoCpus']==1000000000 and ex['ReadonlyRootfs'] and ex['NetworkMode']=='none'
 mounts={x['Destination']:x for x in ex['Mounts']};assert set(mounts)=={'/targets','/work','/evidence'} and mounts['/targets']['Name']=='sail-extension-targets'
 assert mounts['/targets']['RW'] is False and mounts['/work']['RW'] is False and mounts['/evidence']['RW'] is True
 verbs=[]
 for cmd in outer['commands']:
  assert cmd['returncode']==0 and not cmd.get('error');verb=cmd['command'][3];verbs.append(verb)
  for stream in ['stdout','stderr']:assert pin(r/cmd[stream])==cmd[stream+'_file']
  if verb=='ps':assert (r/cmd['stdout']).read_text().strip()==''
  if verb=='wait':assert (r/cmd['stdout']).read_text().strip()=='0'
  if verb in ['start','logs','rm']:assert cmd['command'][-1]==ex['Id']
  if verb=='create':
   for arg in ['--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=64','--user=0:20']:assert arg in cmd['command']
 assert verbs==['ps','image','volume','ps','create','inspect','ps','start','wait','inspect','logs','rm']
 assert outer['host_identity']==dict(uid=501,gid=20) and outer['evidence_permissions']==dict(uid=501,gid=20,mode='0770')
 assert ad['outcome']=='admitted' and ad['verifier_returncode']==0 and ad['reader_identity']==dict(uid=0,gid=20)
 assert ad['boot_id']==BOOT and ad['cgroup']=={'memory.max':'2147483648','memory.swap.max':'0','cpu.max':'100000 100000','pids.max':'64'}
 assert ad['runtime_files']['sail']['sha256']==runtime['sha256'] and ad['runtime_files']['native']['sha256']==q['native_sha256']
 assert ad['versions']==dict(python='3.12.14',pyarrow='21.0.0',numpy='2.5.3')
 assert outer['physical_report']==pin(r/'physical-output.json') and inner['status']==outer['physical_status']==check['physical_status']=='physical_values_pass'
 assert inner['receipt_sha256']==sha(c/'diagnostics/receipt.json') and inner['closure_sha256']==sha(qb/'closed-audit.json') and inner['expected_cell_output']==run['cell_output']
 assert inner['helper_sha256']=='4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872'
 assert inner['expected_vertices']==q['expected_vertices']==16384 and inner['expected_source']==q['expected_source']==0
 assert inner['errors']==[] and inner['physical_failures']=={} and inner['identities_unchanged']
 assert inner['producer_runtime']==runtime['source'] and inner['producer_correctness']==prod['correctness']
 counts=inner['counts'];assert counts['rows']==counts['unique_ids']==16384 and counts['root_rows']==counts['unreachable_rows']==1
 assert all(v==0 for k,v in counts.items() if k not in ['rows','unique_ids','root_rows','unreachable_rows'])
 pins={x['name']:{k:x[k] for k in ['bytes','sha256']} for x in prod['result_files']};assert inner['result_inventory']==pins
 assert len(inner['files'])==len(pins) and {x['name'] for x in inner['files']}==set(pins)
 for file in inner['files']:
  assert file['before']==file['after'] and {k:file['before']['identity'][k] for k in ['bytes','sha256']}==pins[file['name']]
  assert file['streamed_rows']==file['before']['metadata']['rows'] and file['before']['metadata']['schema']=='id: int64\ndistance: double\nhops: int64\nparent: int64'
 assert sum(x['streamed_rows'] for x in inner['files'])==16384
 assert utc(outer['started_utc'])>utc(seq['rows'][-1]['finished_utc'])
 if previous_check:assert utc(outer['started_utc'])>=utc(previous_check)
 previous_check=outer['finished_utc']
 durations=[x['scan_finished_seconds']-x['scan_started_seconds'] for x in samples]
 gaps=[b['scan_started_seconds']-a['scan_started_seconds'] for a,b in zip(samples,samples[1:])]
 hb=load(c/'host-before.json');hostvm=vm(hb['snapshots']['vm_stat']['stdout'])
 rows.append(dict(order=i,phase=row['phase'],runtime=host,outcome='passed',algorithm_iterations=24,seconds=row['seconds'],execution_pss_bytes=row['execution_pss_bytes'],execution_rss_bytes=row['execution_rss_bytes'],cgroup_peak_through_execution_bytes=int(prod['cgroup_execution_after']['memory.peak']),cgroup_lifetime_peak_bytes=int(prod['cgroup_after']['memory.peak']),guest_steal_fraction=0,execution_cpu_deltas={k:cpu1[k]-cpu0[k] for k in cpu0},sample_count=len(samples),execution_sample_count=prod['memory']['phase_sample_counts']['execute'],scan_duration_seconds=dict(min=min(durations),median=statistics.median(durations),max=max(durations)),scan_start_gap_seconds=dict(min=min(gaps),median=statistics.median(gaps),max=max(gaps)),physical_counts=counts,physical_report_sha256=sha(r/'physical-output.json'),outer_receipt_sha256=sha(r/'outer-receipt.json'),producer_receipt_sha256=sha(c/'diagnostics/receipt.json'),host_before_utc=hb['utc'],host_before_vm_stat=hostvm,host_swap_usage=hb['snapshots']['swap']['stdout'].strip(),concurrency_sampling=concurrency))
ratios=[rows[2]['seconds']/rows[3]['seconds'],rows[5]['seconds']/rows[4]['seconds']]
ratio={'adjacent_A_over_B':ratios,'geometric_mean_A_over_B':math.sqrt(math.prod(ratios))}
assert ratio==summary['shared_host_ratios']==serial['original_shared_host_ratios']==audit['shared_host_ratios']
measured=rows[2:]
metrics={}
for k in ['seconds','execution_pss_bytes','execution_rss_bytes','cgroup_peak_through_execution_bytes','cgroup_lifetime_peak_bytes']:
 values={x:statistics.median(r[k] for r in measured if r['runtime']==x) for x in ['A','B']}
 metrics[k]=dict(values,median_B_over_A=values['B']/values['A'],adjacent_B_over_A=[rows[3][k]/rows[2][k],rows[4][k]/rows[5][k]])
after=load(E/'host-pair-execution/host-after.json');aftermeta=load(E/'host-pair-execution/host-after-attribution.json')
assert after['outcome']=='CAPTURED' and after['guest']['boot_identity_stable'] and after['guest']['boot_id']==BOOT
assert aftermeta['plan_sha256']==sha(planpath) and utc(after['started_utc'])>utc(seq['rows'][-1]['finished_utc']) and utc(after['finished_utc'])<utc(serial['started_utc'])
snap=after['host']['snapshots'];assert snap['docker_running']['returncode']==0 and snap['docker_running']['stdout'].strip()==''
lastvm=vm(snap['vm_stat']['stdout']);firstvm=rows[0]['host_before_vm_stat']
host_deltas={k:lastvm[k]-firstvm[k] for k in ['Swapins','Swapouts','Compressions','Decompressions','Pages occupied by compressor','Pageins','Pageouts']}
assert initial=={**inventory(S),**inventory(B),**inventory(R)}
report=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_INDEPENDENT_SIX_CELL_CLOSURE_AND_PHYSICAL_EVIDENCE_AUDIT',blockers=[],audit_source=pin(Path(__file__)),source_preparation=pin(source/'preparation.json'),plan=pin(planpath),pair_requests=pin(B/'pair-requests.json'),collection_audit=pin(E/'host-pair-execution/collection-audit.json'),serial_receipt=pin(R/'serial-receipt.json'),inputs=initial,all_six_rows=rows,shared_host_time_ratios=ratio,measured_metric_comparisons=metrics,whole_host_pressure=dict(before_utc=rows[0]['host_before_utc'],after_utc=after['host']['finished_utc'],after_receipt=pin(E/'host-pair-execution/host-after.json'),attribution=pin(E/'host-pair-execution/host-after-attribution.json'),counters_delta=host_deltas,swap_usage_after=snap['swap']['stdout'].strip(),scope='Whole macOS host between first warmup before-snapshot and post-sequence closure; includes six trials, gaps and later collection interval, not per-cell counters or physical I/O bytes.'),scope=['Six recorded producer reference/parent checks and separate physical finite/domain/metadata checks pass; this reviewer did not recompute Dijkstra or reread Parquet payloads.','AB warmups excluded from measured ABBA; exactly two measurements per runtime, no uncertainty or asymptotic scaling claim.','Time ratios are descriptive on shared Morrobay only. Whole-VM full-trial zero steal and sampled zero sibling containers do not prove dedicated/quiet host, isolate runtime causality or exclude unobserved concurrency.','PSS/RSS are maxima of sampled sums across visible container processes during execute; RSS double-counts shared pages. They differ from cgroup lifetime/through-execution high-water memory including charged cache.','All rows and every memory metric retained. The 50ms sampler interval is sleep after scanning, not guaranteed cadence.','Physical checks all start after the sixth trial and run serially with one CPU/2GiB/swap0/read-only inputs; their time/RSS are not benchmark metrics.','Whole-host paging/compression counts are reported as counts, not physical bytes or workload attribution. No per-cell closure snapshots were collected.'],source_and_collected_inputs_unchanged=True)
with (O/'receipt.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'outcome':report['outcome'],'receipt':pin(O/'receipt.json'),'ratios':ratio,'metrics':metrics,'host_deltas':host_deltas},indent=2))
