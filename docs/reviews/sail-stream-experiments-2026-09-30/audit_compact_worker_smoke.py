#!/usr/bin/env python3
"""Read-only audit of the collected compact561 worker smoke; no remote calls."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'worker-smoke-compact561-cpu16-23'
BINARY = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
RUNTIME = '56194b170155301ba91077f0ba3df31fe2c78b6b'
CONTROLLER = '3a9028057c6c6c5034492845926fc4bc18f9626f'
NATIVE = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
REPO = Path('/Users/alexy/src/sail-large-graphs')
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    collection = read(RUN / 'collection.json')
    assert collection['returncode'] == 0 and not collection['stderr']
    archive = RUN / 'diagnostics.tar'
    assert sha(archive) == collection['sha256'] and archive.stat().st_size == collection['bytes']
    members = []
    with tarfile.open(archive) as tar:
        for item in tar.getmembers():
            assert item.isfile() and Path(item.name).name == item.name, item.name
            data = tar.extractfile(item).read()
            path = RUN / 'diagnostics' / item.name
            assert path.read_bytes() == data, item.name
            members.append(item.name)
    assert sorted(members) == sorted(p.name for p in (RUN/'diagnostics').iterdir())
    config = read(RUN/'configuration.json')
    assert config == read(ROOT/'worker-smoke-compact561-cpu16-23.json')
    receipt = read(RUN/'diagnostics/receipt.json')
    baseline = read(ROOT/'pecan-gate3/measured-1-base/diagnostics/receipt.json')
    previous = read(ROOT/'worker-smoke-instrumented289-cpu16-23/diagnostics/receipt.json')
    result = read(RUN/'result.json')
    orchestration = read(RUN/'cell/orchestration.json')
    assert result['outcome'] == receipt['outcome'] == 'passed'
    assert receipt['binary_sha256'] == BINARY and receipt['runtime_source_sha'] == RUNTIME
    assert receipt['harness_source_sha'] == CONTROLLER and receipt['native_source_sha'] == NATIVE
    assert not receipt['source_dirty'] and not receipt['cleanup_errors'] and not receipt['staging_files_after_shutdown']
    assert receipt['dataset'] == baseline['dataset'] == previous['dataset']
    assert receipt['native_package_identity'] == baseline['native_package_identity'] == previous['native_package_identity']
    assert receipt['dataset']['counts'] == {'vertices':16384,'edges':529723}
    args = receipt['arguments']
    assert args['engine']=='pecan' and args['algorithm']=='sssp' and args['variant']=='frontier'
    assert args['mode']=='process-cluster' and args['traversal_validation']=='reference'
    for name in ('partitions','threads','worker_task_slots','sail_pool_bytes','native_quota','source','directed','seed','max_iterations','timeout','http2_keepalive_timeout','record_plans'):
        assert args[name] == previous['arguments'][name], name
    assert receipt['algorithm_iterations']==24 and receipt['algorithm_converged'] is True
    assert receipt['correctness']=={'rows':16384,'unique':16384,'parent_tree_checked':True,'reference':'independent BFS/heap-Dijkstra'}
    plans = [event for event in receipt['iteration_events'] if event.get('plan')]
    assert len(plans)==24 and all('min(struct(' in event['plan'] for event in plans)
    assert orchestration['attach_returncode']==0 and not orchestration['transport_errors'] and not orchestration['outer_timeout']
    state = orchestration['inspect']['state']
    assert state['ExitCode']==0 and not state['OOMKilled'] and not state['Running']
    limits = orchestration['inspect']['limits']
    assert limits['Memory']==12*(1<<30) and limits['MemorySwap']==12*(1<<30)
    assert limits['CpusetCpus']=='16-23' and limits['NanoCpus']==8_000_000_000
    for key in ('cgroup_execution_before','cgroup_execution_after','cgroup_after'):
        cg=receipt[key];assert cg['memory.max']=='12884901888' and cg['memory.swap.max']=='0'
        assert cg['cpu.max']=='800000 100000' and cg['cpuset.cpus.effective']=='16-23'
        events=dict(line.split() for line in cg['memory.events'].splitlines())
        assert events['oom']=='0' and events['oom_kill']=='0'
    admission=read(ROOT/'worker-smoke-561-admission.json')
    assert admission['outcome']=='passed' and admission['config_sha256']==sha(RUN/'configuration.json')
    assert not admission['running_before']['stdout'].strip() and not admission['running_after']['stdout'].strip()
    known_manifest=read(ROOT/'worker-smoke-manifest-check.json')['remote_manifest']['sha256']
    assert admission['observed']['datasets']['weighted16k']['sha256']==known_manifest
    assert admission['observed']['binary_sha256']==BINARY
    build=read(ROOT/'linux-builds/compact561-host/final/rebuild-receipt.json')
    assert build['outcome']=='passed' and build['source_sha']==RUNTIME and build['host']['sha256']==BINARY
    assert datetime.fromisoformat(build['finished_utc']) < datetime.fromisoformat(receipt['started_utc'])
    capture=read(RUN/'process-identity-01.json')
    assert capture['outcome']=='capture_error' and capture['inspect']['returncode']!=0
    assert 'no such object' in capture['inspect']['stderr']

    lines=(RUN/'diagnostics/server.log').read_text().splitlines()
    header=re.compile(r'\] job (\d+) stage (\d+) partition (\d+) attempt (\d+) execution plan$')
    status=re.compile(r'worker_task_status worker_id=(\d+) job_id=(\d+) stage=(\d+) partition=(\d+) attempt=(\d+) status=(\w+)')
    statuses=defaultdict(list)
    successes=Counter()
    for number,line in enumerate(lines,1):
        match=status.search(line)
        if match:
            worker,job,stage,partition,attempt,state=match.groups()
            statuses[tuple(map(int,(job,stage,partition,attempt)))].append((int(worker),state,number))
            if state=='SUCCEEDED':successes[int(worker)]+=1
    aggregate_tasks=[]
    for offset,line in enumerate(lines):
        match=header.search(line)
        if not match:continue
        nodes=[]
        for number,following in enumerate(lines[offset+1:],offset+2):
            if following.startswith('['):break
            if 'AggregateExec:' in following and 'min(struct(' in following:
                nodes.append({'line':number,'mode':re.search(r'mode=(\w+)',following).group(1)})
        if not nodes:continue
        key=tuple(map(int,match.groups()));events=statuses[key]
        good=[(worker,n) for worker,state,n in events if state=='SUCCEEDED']
        running=[(worker,n) for worker,state,n in events if state=='RUNNING']
        assert len(good)==len(running)==1 and good[0][0]==running[0][0],key
        assert all(state in ('RUNNING','SUCCEEDED') for _,state,_ in events),key
        aggregate_tasks.append({'job':key[0],'stage':key[1],'partition':key[2],'attempt':key[3],
            'worker':good[0][0],'plan_header_line':offset+1,'aggregate_nodes':nodes,
            'running_line':running[0][1],'succeeded_line':good[0][1]})
    assert aggregate_tasks and {row['worker'] for row in aggregate_tasks}=={1,2}
    modes=Counter((row['worker'],node['mode']) for row in aggregate_tasks for node in row['aggregate_nodes'])
    assert all(modes[worker,mode]>0 for worker in (1,2) for mode in ('Partial','FinalPartitioned'))
    worker_starts=[]
    start=re.compile(r'extension process worker (\d+): pid=Some\((\d+)\), driver_pid=(\d+), session=([^\s]+)')
    for number,line in enumerate(lines,1):
        m=start.search(line)
        if m:worker_starts.append({'worker':int(m[1]),'pid':int(m[2]),'driver_pid':int(m[3]),'line':number})
    assert sorted(row['worker'] for row in worker_starts)==[1,2]
    assert {row['driver_pid'] for row in worker_starts}=={receipt['driver_pid']}
    source_refs={
      'graph_cell.py':(CONTROLLER,'examples/extensions/benchmarks/graph_cell.py'),
      'traversal_cell.py':(CONTROLLER,'examples/extensions/benchmarks/traversal_cell.py'),
      'compact_struct_min.rs':(RUNTIME,'crates/sail-function/src/aggregate/compact_struct_min.rs'),
      'struct_min.rs':(RUNTIME,'crates/sail-function/src/aggregate/struct_min.rs')}
    sources={}
    for name,(ref,path) in source_refs.items():
        data=subprocess.check_output(['git','-C',str(REPO),'show',ref+':'+path])
        sources[name]={'commit':ref,'path':path,'sha256':hashlib.sha256(data).hexdigest()}
    inventory=[{'path':str(p.relative_to(RUN)),'bytes':p.stat().st_size,'sha256':sha(p)}
               for p in sorted(RUN.rglob('*')) if p.is_file() and p.name not in ('verification.json','aggregate-task-audit.json')]
    (RUN/'aggregate-task-audit.json').write_text(json.dumps({'recorded_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Observed min(struct) plan nodes paired by full job/stage/partition/attempt key with same-worker RUNNING and SUCCEEDED events',
        'tasks':aggregate_tasks},indent=2)+'\n')
    verification={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'passed',
      'binary_sha256':BINARY,'runtime_source_sha':RUNTIME,'harness_source_sha':CONTROLLER,'native_source_sha':NATIVE,
      'algorithm_iterations':24,'plan_count':24,'verification':receipt['correctness'],
      'validation_tolerance':'abs(distance-expected) <= 1e-12 * (1 + abs(expected)); reachability and unique ID coverage exact; rooted parent/hop checks',
      'dataset_and_original_native_equal_to':['pecan-gate3/measured-1-base/diagnostics/receipt.json','worker-smoke-instrumented289-cpu16-23/diagnostics/receipt.json'],
      'dataset_manifest_sha256':known_manifest,'preflight_manifest_matches_retained_baseline':True,
      'diagnostic_archive_members_verified':members,'worker_completed_task_notifications':dict(successes),
      'worker_process_start_records':worker_starts,'grouped_tuple_min_tasks_correlated':len(aggregate_tasks),
      'grouped_tuple_min_nodes_by_worker_and_mode':[{'worker':w,'mode':m,'nodes':n} for (w,m),n in sorted(modes.items())],
      'source_review':sources,'guest_steal_fraction':receipt['guest_steal_fraction'],
      'no_recorded_cgroup_oom':True,'cleanup_errors':[],
      'late_process_identity_observation':'capture_error retained after automatic container removal; no host/container PID namespace map obtained. Startup worker IDs/PIDs and explicit task success are independently present in server log.',
      'runtime_path_scope':'Actual min(struct) task plans and success on runtime561 with eligible production Float64/Int64/Int64 expression; selection of compact grouped state follows pinned source factory. Plan display alone does not expose accumulator allocation layout.',
      'oracle_scope':'Auditor verifies recorded producer reference checks and their pinned source; result Parquet files remain in target volume, were not downloaded or recomputed by this audit.',
      'comparison_scope':'Functional smoke on shared host after build completion. Prior289 smoke overlapped build: no elapsed-time or memory comparison/ratio claimed.',
      'no_new_workload_by_auditor':True,'files':inventory,'audit_script_sha256':sha(Path(__file__))}
    (RUN/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    print(json.dumps({'outcome':'passed','worker_success_notifications':dict(successes),
        'aggregate_tasks_correlated':len(aggregate_tasks),'aggregate_nodes':verification['grouped_tuple_min_nodes_by_worker_and_mode'],
        'verification_sha256':sha(RUN/'verification.json')}))


if __name__=='__main__':main()
