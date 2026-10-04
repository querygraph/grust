"""Offline audit of the four closed WCC pilot archives. No runtime or payload scan.

Run: python3 audit.py --directory PATH_CONTAINING_ARCHIVES_AND_PILOT --output NEW.json
The audited pilot performed full physical oracle comparison. This tool verifies
that producer evidence, closure, identities and recomputes diagnostic metrics.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import tarfile
import tempfile
import traceback

CASES = [
 ('cell01-local-randomized.tar.gz', 'sem-wcc-01b-local-randomized', 'local', 'randomized'),
 ('cell02-cluster-randomized.tar.gz', 'sem-wcc-02-cluster-randomized', 'process-cluster', 'randomized'),
 ('cell03-cluster-fused.tar.gz', 'sem-wcc-03-cluster-fused', 'process-cluster', 'randomized_fused'),
 ('cell04-local-fused.tar.gz', 'sem-wcc-04-local-fused', 'local', 'randomized_fused'),
]
PILOT = '61fae920ae66936e517ae85e2abcb72266114d22735014c2781959c3a48e1731'
WRAPPER = '39a1108a7c68d770e945b97cfa0cbbd6f7d3eb16fc6b8b40d0ae913f4215582b'
CONTROLLER = '3a9028057c6c6c5034492845926fc4bc18f9626f'
RUNTIME = '56194b170155301ba91077f0ba3df31fe2c78b6b'
NATIVE = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
NATIVE_SO = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
INPUTS = {
 'cit-Patents-v.parquet':'0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa',
 'cit-Patents-e.parquet':'70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f',
 'wcc-membership.i64le':'b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc'}
GIB = 2**30


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    return json.loads(path.read_text())


def counters(text):
    return {k:int(v) for k,v in (line.split() for line in text.splitlines())}


def distribution(values):
    return dict(count=len(values), minimum=min(values), median=statistics.median(values), maximum=max(values), total=sum(values)) if values else None


def archive_case(directory, case):
    name, run_id, mode, method = case
    archive = directory/name
    before = sha(archive)
    with tempfile.TemporaryDirectory(prefix='wcc-closed-audit-') as temp:
        root = Path(temp)
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            names = [str(Path(m.name)) for m in members]
            require(len(set(names)) == len(names), 'duplicate normalized archive member')
            require(sum(m.size for m in members) <= 128*2**20, 'unexpected archive expansion')
            for m in members:
                require(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and (m.isfile() or m.isdir()) and not m.issym() and not m.islnk(), 'unsafe archive member')
            bundle.extractall(root, filter='data')
        files = {str(p.relative_to(root)):dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(root.rglob('*')) if p.is_file()}
        r, c, o, z = [load(root/p) for p in ('diagnostics/receipt.json','configuration.json','cell/orchestration.json','result.json')]
        admission = load(root/'admission.json')
        require(admission['returncode'] == 0, 'admission failure')
        admitted = json.loads(admission['stdout'])
        require(r['outcome'] == z['outcome'] == z['producer_outcome'] == 'passed', 'producer or closure not passed')
        require(r['controller'] == c['config']['harness_source_sha'] == CONTROLLER and r['runtime'] == RUNTIME and r['native'] == NATIVE, 'source identity mismatch')
        require(r['helper_sha256'] == c['pilot_sha256'] == admitted['pilot_sha256'] == PILOT and c['host_wrapper_sha256'] == WRAPPER, 'helper mismatch')
        require(r['native_package_identity']['files_sha256']['_native.cpython-312-x86_64-linux-gnu.so'] == NATIVE_SO, 'native mismatch')
        require(r['input_hashes_before'] == r['input_hashes_after'] and {Path(k).name:v for k,v in r['input_hashes_before'].items()} == INPUTS, 'input/oracle identity mismatch')
        require(r['arguments']['mode'] == mode and r['arguments']['method'] == method and r['arguments']['timeout'] == 1200, 'mode/method/cap mismatch')
        require(c['config']['run_id'] == run_id and Path(r['arguments']['output']).name == run_id, 'namespace mismatch')
        require(c['command'] == o['command'][o['command'].index(IMAGE)+1:], 'actual command mismatch')
        command_args = dict(zip(c['command'][3::2], c['command'][4::2]))
        require(command_args == {'--'+k:str(v) for k,v in r['arguments'].items()}, 'producer arguments differ from command')
        require(c['config']['limits'] == dict(cpus=16,cpuset_cpus='0-15',memory_gib=32,outer_timeout_seconds=2700), 'declared limits mismatch')
        limits = o['inspect']['limits']
        require(limits['Memory'] == limits['MemorySwap'] == 32*GIB and limits['NanoCpus'] == 16*10**9 and limits['CpusetCpus'] == '0-15' and limits['PidMode'] == '' and limits['Init'] is True, 'actual envelope mismatch')
        require(o['inspect']['image'] == c['config']['image'] == IMAGE, 'image mismatch')
        processes = 1 if mode == 'local' else 3
        resources = r['resources']
        require(resources['pool_per_process_bytes'] == (24//processes)*GIB and resources['potential_pool_total_bytes'] == 24*GIB, 'pool configuration mismatch')
        require(resources['worker_count'] == processes-1 and resources['partitions'] == 16 and resources['threads_per_process'] == 16 and resources['worker_slots'] == 64, 'parallelism mismatch')
        require(resources['native_quota_per_process_bytes'] == 256*2**20 and resources['potential_native_total_bytes'] == processes*256*2**20, 'native reservation mismatch')
        for key in ('cgroup_before','cgroup_execution_before','cgroup_execution_after','cgroup_after'):
            cg = r[key]
            require(cg['memory.max'] == str(32*GIB) and cg['memory.swap.max'] == '0' and cg['cpu.max'] == '1600000 100000' and cg['cpuset.cpus.effective'] == '0-15', 'cgroup envelope mismatch')
            require(all(v == 0 for v in counters(cg['memory.events']).values()), 'memory events present')
        require(o['create']['returncode'] == o['attach_returncode'] == o['remove']['returncode'] == 0 and not o['outer_timeout'] and not o['transport_errors'], 'container closure incomplete')
        state = o['inspect']['state']
        require(state == z['container_state'] and state['ExitCode'] == 0 and state['OOMKilled'] is False and state['Running'] is False, 'container did not exit cleanly')
        require(not r['cleanup_errors'] and r['graphutils_staging_root_verified'] and r['staging_files_after_shutdown'] == [] and r['memory']['error'] is None and r['memory']['thread_alive'] is False, 'cleanup or sampler incomplete')
        require(r['converged'] is True and r['iterations'] == 19, 'convergence mismatch')
        correctness = r['correctness']
        require(type(correctness['rows']) is int and correctness['rows'] == correctness['unique'] == 3774768 and correctness['membership_mismatches'] == 0 and correctness['components'] == 3627 and correctness['largest_component_vertices'] == 3764117, 'full oracle receipt mismatch')
        require(correctness['canonicalization'] == 'exact minimum original vertex ID' and 'PyArrow full physical output' in correctness['verification'], 'incorrect verification scope')
        require(len(correctness['result_files']) > 0 and all(v['bytes'] > 0 and re.fullmatch('[0-9a-f]{64}',v['sha256']) for v in correctness['result_files'].values()), 'missing output hash inventory')
        require(load(root/'collection.json')['returncode'] == 0, 'collection failed')
        require(load(root/'diagnostics/server-settings.json')['rust_log'] == 'info,sail_execution::task_runner=debug', 'logging filter changed')
        samples = [json.loads(x) for x in (root/'diagnostics/memory-samples.jsonl').read_text().splitlines()]
        events = [json.loads(x) for x in (root/'diagnostics/events.jsonl').read_text().splitlines()]
        require([{k:v for k,v in x.items() if k != 'recorded_utc'} for x in events] == r['events'], 'event copies differ')
        require(len(samples) == r['memory']['samples'] and Counter(x['phase'] for x in samples) == r['memory']['phase_sample_counts'], 'sample count mismatch')
        require(len({x['scan_started_seconds'] for x in samples}) == len(samples), 'duplicate sample timestamp')
        for phase, peaks in r['memory']['phase_peaks'].items():
            for key, expected in peaks.items():
                require(max(x[key] for x in samples if x['phase'] == phase and x[key] is not None) == expected, 'sample peak mismatch')
        rounds = []
        for iteration in range(1,20):
            start, end = [e for e in events if e['iteration'] == iteration]
            require((start['kind'],end['kind']) == ('iteration_start','iteration_end'), 'round boundary mismatch')
            rounds.append(end['elapsed_seconds']-start['elapsed_seconds'])
        require(rounds == [x['seconds'] for x in r['rounds']['completed_round_durations']] and events[-1]['edges_after'] == 0 and not r['rounds']['incomplete_rounds'], 'round totals mismatch')
        phase = dict(pre_first_round=r['rounds']['pre_first_round_seconds'],contraction_rounds=sum(rounds),post_last_round=r['rounds']['post_last_round_seconds'],export=r['export_seconds'])
        phase['inter_round_gaps'] = r['algorithm_ready_seconds']-sum(phase[k] for k in ('pre_first_round','contraction_rounds','post_last_round'))
        timer = r['end_to_end_seconds']
        cpu = {}
        for label,before_key,after_key in [('pre_execution','cgroup_before','cgroup_execution_before'),('execution','cgroup_execution_before','cgroup_execution_after'),('verification_and_cleanup','cgroup_execution_after','cgroup_after')]:
            b,a = counters(r[before_key]['cpu.stat']),counters(r[after_key]['cpu.stat'])
            cpu[label] = {k:a[k]-v for k,v in b.items()}
        scans = {}
        for phase_name in sorted({x['phase'] for x in samples}):
            subset = [x for x in samples if x['phase'] == phase_name]
            scans[phase_name] = dict(scan_wall_seconds=distribution([x['scan_finished_seconds']-x['scan_started_seconds'] for x in subset]), start_gap_seconds=distribution([b['scan_started_seconds']-a['scan_started_seconds'] for a,b in zip(subset,subset[1:])]),directory_scans=sum(x['directories'] is not None for x in subset))
        server = (root/'diagnostics/server.log').read_text()
        workers = [(int(w),int(p),int(d)) for w,p,d in re.findall(r'extension process worker (\d+): pid=Some\((\d+)\), driver_pid=(\d+)',server)]
        require(sorted(w for w,p,d in workers) == list(range(1,processes)), 'worker identity mismatch')
        seen_pids = {p['pid'] for row in samples for p in row['processes']}
        require(all(d == r['driver_pid'] and p in seen_pids and f'worker {w} server has stopped' in server for w,p,d in workers), 'worker closure mismatch')
        require(sha(archive) == before, 'archive changed during audit')
        summary = dict(archive=name,archive_sha256=before,archive_bytes=archive.stat().st_size,collected_files=files,
            outcome='PASS_INDEPENDENT_COLLECTED_CLOSURE_AUDIT',run_id=run_id,mode=mode,method=method,boot_id=admitted['boot_id'],
            correctness={k:v for k,v in correctness.items() if k != 'result_files'},result_files=correctness['result_files'],resources=resources,worker_pids=workers,
            timer_seconds=timer,algorithm_ready_seconds=r['algorithm_ready_seconds'],iterations=r['iterations'],converged=r['converged'],
            phases={k:dict(seconds=v,fraction_public_timer=v/timer) for k,v in phase.items()},
            input_snapshot_and_validation_seconds=r['input_snapshot_and_validation_seconds'],input_snapshot_materialize_seconds=r['input_snapshot_materialize_seconds'],input_validation_and_count_seconds=r['input_validation_and_count_seconds'],
            verification_seconds=r['verification_seconds'],cpu_phase_delta=cpu,execution_system_cpu_fraction=cpu['execution']['system_usec']/cpu['execution']['usage_usec'],execution_average_used_cores=cpu['execution']['usage_usec']/1e6/timer,
            cgroup_lifetime_peak_bytes=int(r['cgroup_after']['memory.peak']),execute_sampled_memory=r['memory']['phase_peaks']['execute'],sampler=scans,
            guest_steal_fraction=r['guest_steal_fraction'],server_log_bytes=files['diagnostics/server.log']['bytes'],host_before=load(root/'host-before.json'))
        return summary,r,c


def ratio(current, prior):
    return dict(numerator=current,denominator=prior,ratio=current/prior,change_percent=(current/prior-1)*100)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('.'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=dict(started_utc=datetime.now(timezone.utc).isoformat(),outcome='INCONCLUSIVE',audit_source_sha256=sha(Path(__file__)))
    try:
        require(sha(args.directory/'pilot.py') == PILOT and sha(args.directory/'run_one.py') == WRAPPER, 'audited helper sources changed')
        cases=[archive_case(args.directory,c) for c in CASES]
        summaries=[x[0] for x in cases]
        first,first_config=cases[0][1:]
        for summary,r,c in cases:
            require({k:v for k,v in c['config'].items() if k != 'run_id'} == {k:v for k,v in first_config['config'].items() if k != 'run_id'},'config parity changed')
            for k in ('input_hashes_before','input_hashes_after','controller','runtime','native','native_package_identity','packages','helper_sha256','timer_boundary','validation_boundary','diagnostic_boundary','client_thread_environment','iterations','converged'):
                require(r[k] == first[k], 'comparison identity differs: '+k)
            require(summary['boot_id'] == summaries[0]['boot_id'],'guest reboot between cells')
            require([{k:v for k,v in e.items() if k not in ('elapsed_seconds','algorithm')} for e in r['events']] == [{k:v for k,v in e.items() if k not in ('elapsed_seconds','algorithm')} for e in first['events']], 'contraction choices/counts differ')
        comparisons={}
        for label,n,d in [('randomized_cluster_over_local',1,0),('fused_cluster_over_local',2,3),('local_fused_over_randomized',3,0),('cluster_fused_over_randomized',2,1)]:
            a,b=summaries[n],summaries[d]
            comparisons[label]=dict(public_timer=ratio(a['timer_seconds'],b['timer_seconds']),cgroup_peak=ratio(a['cgroup_lifetime_peak_bytes'],b['cgroup_lifetime_peak_bytes']),sampled_pss=ratio(a['execute_sampled_memory']['pss_bytes'],b['execute_sampled_memory']['pss_bytes']),execution_cpu=ratio(a['cpu_phase_delta']['execution']['usage_usec'],b['cpu_phase_delta']['execution']['usage_usec']),phases={k:ratio(a['phases'][k]['seconds'],b['phases'][k]['seconds']) for k in ('pre_first_round','contraction_rounds','post_last_round','export')})
        require(sha(args.directory/'pilot.py') == PILOT and sha(args.directory/'run_one.py') == WRAPPER,'helper source changed during audit')
        result.update(outcome='PASS_INDEPENDENT_FOUR_CELL_CLOSURE_AUDIT',cases=summaries,comparisons=comparisons,same_contraction_choices_and_counts=True,
            scope=['All four producer receipts report full independent PyArrow physical output versus pinned union-find membership. Auditor verifies source guards/closed receipts/output hash inventory, not remote Parquet payloads.',
                   'Runtime binary hash5b7f506c is enforced before/after by frozen pilot; this audit does not independently reread remote binaries.',
                   'Outer archives/member bytes are hashed. Omitted original diagnostics.tar digests are retained but cannot independently be rehashed here.',
                   'Public timer starts after lazy input handles are created, through unchanged public WCC call and full output write; startup/input hash preparation/oracle verification excluded.',
                   'Single samples in order local randomized,cluster randomized,cluster fused,local fused. Shared-host descriptive ratios, no dedicated speed rating, randomized repetitions, external-engine parity or scaling proof.',
                   'Same16CPU/32GiB cap and nominal24GiB aggregate pool. Local24GiB versus8GiB/process in cluster; configured native reservations256MiB versus768MiB aggregate. Each process receives Tokio/Rayon width16, not a fixed aggregate thread count.',
                   'Same debug filter emits different logging volumes; local actual task-plan coverage absent. Logging overhead was not isolated.',
                   'Zero guest steal/no container OOM do not establish quiet macOS host. Only host-before paging/compression snapshots, no per-cell host-after deltas.',
                   'System CPU covers every cgroup process; not evidence of particular syscalls/I/O or a causal bottleneck. Sampler scan elapsed sum is wall occupancy, not CPU cost or subtractable overhead.',
                   'Sampler50ms is sleep after scan; actual cadence and phase metrics are recomputed from complete rows. Snapshot residual includes validation/count and Python/control work, not a pure scan.',
                   'Empty staging evidence means no Parquet remains under verified root. Shutdown actor-abort task counts are not used as job counts.'])
    except BaseException:
        result.update(outcome='AUDIT_ERROR_OR_INCONCLUSIVE',error=traceback.format_exc())
    result['finished_utc']=datetime.now(timezone.utc).isoformat()
    with args.output.open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(outcome=result['outcome'],receipt=str(args.output),sha256=sha(args.output))))
    return 0 if result['outcome'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
