"""Read local closed logging03 evidence only; no runtime or output-data execution."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import tarfile

OUT=Path(__file__).resolve().parent
EXP=OUT.parent
REPO=EXP.parents[2]
CELL=EXP/'logging03-compact'
inputs={}


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def bind(path,expected=None):
    assert path.is_file() and not path.is_symlink()
    value=dict(bytes=path.stat().st_size,sha256=sha(path))
    if expected is not None:assert value==expected,(path,'pin differs')
    inputs[str(path.relative_to(REPO))]=value
    return value


def load(path):
    bind(path)
    return json.loads(path.read_text())


def counters(text):
    return {key:int(value) for key,value in (line.split() for line in text.splitlines())}


def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        return [row for k in sorted(set(a)|set(b)) for row in differences(a.get(k),b.get(k),path+'/'+k)]
    if a!=b:return [dict(path=path,logging02=a,logging03=b)]
    return []


def host_counters(snapshot):
    text=snapshot['vm_stat']['stdout']
    page_size=int(re.search(r'page size of (\d+) bytes',text)[1])
    keys=['Pages occupied by compressor','Pages stored in compressor','Compressions','Decompressions','Swapins','Swapouts','Pageins','Pageouts']
    return dict(page_size_bytes=page_size,swap_used_M=float(re.search(r'used = ([0-9.]+)M',snapshot['swap']['stdout'])[1]),
                counters={k:int(re.search(re.escape(k)+r':\s*(\d+)\.',text)[1]) for k in keys})


def main():
    started=datetime.now(timezone.utc).isoformat()
    result=load(CELL/'result.json');r=load(CELL/'diagnostics/receipt.json')
    old=load(EXP/'logging02/diagnostics/receipt.json')
    verification=load(EXP/'closed-cell-audit/logging03-verification.json')
    old_verification=load(EXP/'closed-cell-audit/logging02-verification.json')
    config=load(CELL/'configuration.json');c2=load(EXP/'logging02.json')
    recovery=load(EXP/'logging03-recovery02.json');closure=load(EXP/'logging03-host-closure.json')
    transfer=load(EXP/'logging03-collection.json');collection=load(CELL/'collection.json')
    orchestration=load(CELL/'cell/orchestration.json');before=load(CELL/'host-before.json')
    prelaunch=load(EXP/'logging03-prelaunch-audit/receipt.json')
    bind(EXP/'compact-qualification-review/REVIEW.md')
    bind(EXP/'physical-output-audit/README.md')
    bind(EXP/'parquet-float-statistics/README.md')
    assert verification['integrity_status']=='integrity_verified' and verification['errors']==verification['inconclusive_reasons']==[]
    assert verification['correctness_verification']=='not_performed'
    for name,pin in verification['files'].items():
        path=Path(name) if Path(name).is_absolute() else REPO/name
        assert path.is_relative_to(REPO)
        bind(path,pin)
    assert transfer['returncode']==collection['returncode']==0
    assert (CELL/'diagnostics.tar').stat().st_size==collection['bytes'] and sha(CELL/'diagnostics.tar')==collection['sha256']
    members={}
    with tarfile.open(CELL/'diagnostics.tar','r:') as archive:
        for member in archive:
            assert member.isfile() and '/' not in member.name and member.name not in members
            h=hashlib.sha256();size=0
            with archive.extractfile(member) as f:
                for block in iter(lambda:f.read(1<<20),b''):size+=len(block);h.update(block)
            local=CELL/'diagnostics'/member.name
            assert size==member.size==local.stat().st_size and h.hexdigest()==sha(local)
            members[member.name]=dict(bytes=size,sha256=h.hexdigest())
    assert set(members)=={'receipt.json','server.log','server-settings.json','memory-samples.jsonl'}
    assert result['outcome']==result['receipt_outcome']==r['outcome']=='passed'
    assert r['source_dirty'] is False and r['harness_source_sha']==config['harness_source_sha']=='3a9028057c6c6c5034492845926fc4bc18f9626f'
    assert r['runtime_source_sha']==config['runtime_source_sha']=='56194b170155301ba91077f0ba3df31fe2c78b6b'
    assert r['binary_sha256']=='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
    assert r['native_source_sha']==old['native_source_sha']=='ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
    assert r['native_package_identity']==old['native_package_identity'] and r['dataset']==old['dataset']
    config_diff=differences(c2,config)
    assert config_diff==prelaunch['exactly_seven_configuration_differences']
    assert set(x['path'] for x in differences(old['arguments'],r['arguments']))=={'/sail_binary','/runtime_source_sha','/output'}
    a=r['arguments'];assert (a['engine'],a['algorithm'],a['variant'],a['source'],a['directed'],a['delta'])==('pecan','sssp','delta_star',13507776,False,0.1)
    assert a['traversal_validation']=='certificate' and a['partitions']==a['threads']==32 and a['worker_task_slots']==64
    assert r['algorithm_iterations']==60 and r['algorithm_converged'] is True
    for name in ['algorithm_ready_seconds','end_to_end_seconds']:
        assert type(r[name]) in (int,float) and math.isfinite(r[name]) and r[name]>0
    events=r['iteration_events'];assert len(events)==120
    for i in range(60):
        start,end=events[2*i:2*i+2]
        assert (start['kind'],end['kind'])==('iteration_start','iteration_end')
        assert start['iteration']==end['iteration']==i+1 and start['bucket']==end['bucket']
    elapsed=[e['elapsed_seconds'] for e in events]
    assert elapsed==sorted(elapsed) and elapsed[-1]<=r['algorithm_ready_seconds']<=r['end_to_end_seconds']
    correctness=r['correctness']
    assert correctness['rows']==correctness['unique']==16777216 and correctness['reached']==8862601
    assert correctness['certificate']=='all-edge inequalities and rooted tight-edge reachability'
    assert correctness['reference']=='distributed certificate; no precomputed reference vector'
    assert correctness['parent_tree_checked'] is True and correctness['witness_rounds']==22
    assert correctness['relative_edge_tolerance']==1e-12
    assert correctness['conservative_absolute_distance_error_bound']==(correctness['rows']-1)*correctness['max_edge_slack']
    state=orchestration['inspect']['state']
    assert state['ExitCode']==0 and state['OOMKilled'] is False and state['Running'] is False and state['Status']=='exited'
    assert orchestration['attach_returncode']==0 and orchestration['outer_timeout'] is False and orchestration['transport_errors']==[]
    assert orchestration['remove']['returncode']==0 and r['cleanup_errors']==[] and r['staging_files_after_shutdown']==[]
    assert recovery['returncode']==0 and recovery['capture']['commands']['running_containers']['stdout']==''
    assert recovery['capture']['commands']['supervisor_pids']['returncode']==1
    for name,item in recovery['capture']['files'].items():
        assert sha(CELL/name)==item['sha256'] and (CELL/name).stat().st_size==item['bytes']
    cgroup={name:r[name] for name in ['cgroup_before','cgroup_execution_before','cgroup_execution_after','cgroup_after']}
    for snapshot in cgroup.values():
        assert snapshot['memory.max']=='107374182400' and snapshot['memory.swap.max']=='0' and snapshot['cpu.max']=='3200000 100000' and snapshot['cpuset.cpus.effective']=='0-31'
        assert all(counters(snapshot['memory.events'])[k]==0 for k in ['max','oom','oom_kill','oom_group_kill'])
    memory=r['memory'];assert memory['execution_sampled'] is True and memory['thread_alive'] is False and memory['error'] is None
    counts=Counter();peaks=defaultdict(lambda:defaultdict(int));durations=[];gaps=[];previous=None
    with (CELL/'diagnostics/memory-samples.jsonl').open() as stream:
        for line in stream:
            row=json.loads(line);phase=row['phase'];counts[phase]+=1
            start,end=row['scan_started_seconds'],row['scan_finished_seconds']
            assert end>=start
            durations.append(end-start)
            if previous is not None:
                assert start>=previous;gaps.append(start-previous)
            previous=start
            for field in ['rss_bytes','pss_bytes','cgroup_current_bytes','fd_total']:
                if row[field] is not None:peaks[phase][field]=max(peaks[phase][field],row[field])
    assert sum(counts.values())==memory['samples']==30166 and dict(counts)==memory['phase_sample_counts']
    for phase,values in memory['phase_peaks'].items():assert dict(peaks[phase])==values
    assert old_verification['recorded_outcomes']['runner_outcome']=='oom' and old['outcome']=='error'
    assert all(k not in old for k in ['end_to_end_seconds','algorithm_ready_seconds','algorithm_iterations','correctness'])
    host_before=host_counters(before['snapshots']);host_after=host_counters(closure['host']['snapshots'])
    assert host_before['page_size_bytes']==host_after['page_size_bytes']==4096
    host_delta={k:host_after['counters'][k]-v for k,v in host_before['counters'].items()}
    assert all(v>=0 for k,v in host_delta.items() if k not in ['Pages occupied by compressor','Pages stored in compressor'])
    # Scan without emitting any potentially sensitive matching text.
    patterns={
        'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
        'aws_access_key':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
        'github_token':re.compile(rb'\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
        'openai_style_token':re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
        'authorization':re.compile(rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}'),
    }
    hits=Counter();lines=0
    with (CELL/'diagnostics/server.log').open('rb') as stream:
        for line in stream:
            lines+=1
            for name,pattern in patterns.items():
                if pattern.search(line):hits[name]+=1
    report=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),started_utc=started,
        outcome='CLOSED_PRODUCER_PASS_AND_COLLECTION_CONFIRMED_PHYSICAL_VALUES_UNVERIFIED',inputs=inputs,
        identity=dict(runtime_sha=r['runtime_source_sha'],binary_sha256=r['binary_sha256'],harness_sha=r['harness_source_sha'],native_sha=r['native_source_sha'],native_identity_matches_logging02=True,dataset_manifest_matches_logging02=True,configuration_differences=config_diff),
        producer=dict(algorithm='Pecan SSSP delta_star',source=a['source'],directed=a['directed'],delta=a['delta'],iterations=r['algorithm_iterations'],converged=r['algorithm_converged'],algorithm_ready_seconds=r['algorithm_ready_seconds'],end_to_end_seconds=r['end_to_end_seconds'],boundary=r['boundary'],cache_boundary=r['cache_boundary'],correctness=correctness,result_files=r['result_files'],result_total_bytes=sum(f['bytes'] for f in r['result_files'])),
        collection=dict(archive_sha256=collection['sha256'],archive_bytes=collection['bytes'],members=members,all_member_bytes_equal_local=True,closed_helper_correctness_verification=verification['correctness_verification']),
        closure=dict(docker_state=state,outer_timeout=False,attach_returncode=0,transport_errors=[],producer_cleanup_errors=[],staging_inventory_after_shutdown=[],removed=True,recovery_observed_no_containers_or_supervisor=True,original_launch_tool_wrapper_exit=recovery['original_launch_tool_wrapper_exit']),
        memory=dict(phase_peaks=memory['phase_peaks'],phase_sample_counts=dict(counts),kernel_cgroup_peak_bytes=int(r['cgroup_after']['memory.peak']),cgroup_execute_end_peak_bytes=int(r['cgroup_execution_after']['memory.peak']),memory_events_after=counters(r['cgroup_after']['memory.events']),execute_cpu_counter_delta={k:counters(r['cgroup_execution_after']['cpu.stat'])[k]-v for k,v in counters(r['cgroup_execution_before']['cpu.stat']).items()},sample_scan_duration_seconds=dict(min=min(durations),median=statistics.median(durations),max=max(durations)),sample_start_gap_seconds=dict(min=min(gaps),median=statistics.median(gaps),max=max(gaps)),sample_error=memory['error'],scope=memory['scope'],pss_boundary=memory['pss_boundary'],cgroup_boundary=memory['cgroup_boundary']),
        host=dict(guest_steal_fraction=r['guest_steal_fraction'],steal_scope=r['steal_scope'],before_utc=before['utc'],closure_started_utc=closure['host']['started_utc'],before=host_before,after=host_after,counter_delta=host_delta,scope='Whole macOS host before cell to post-cell closure about eight minutes after container exit; counters are not cell-specific physical I/O or causal attribution. Zero guest steal/container swap does not establish a quiet host.'),
        baseline=dict(runner_outcome='oom',producer_outcome=old['outcome'],elapsed_until_error_seconds=old['elapsed_until_error_seconds'],completed_execution_time=None,certificate=None,events=[{k:v for k,v in e.items() if k!='plan'} for e in old['iteration_events']],sampled_execute_peaks=old['memory']['phase_peaks']['execute'],cgroup_peak_bytes=int(old['cgroup_after']['memory.peak']),memory_events=counters(old['cgroup_after']['memory.events'])),
        privacy=dict(server_log_bytes=(CELL/'diagnostics/server.log').stat().st_size,server_log_lines=lines,credential_pattern_matched_lines=dict(hits),scope='Five explicit credential families scanned linewise; values never emitted. Not exhaustive privacy review. No compression, rewrite or staging performed.'),
        limits=['No completed logging02 denominator: no completion-speed ratio or absolute performance qualification.', 'Single sequential shared-host diagnostic pair; host pressure/cache state and host-wide paging differ, and no causal attribution follows from0VMsteal.', 'Producer certificate uses bounded floating tolerance and rooted parent witnesses, not a bitwise reference vector or independent Dijkstra result.', 'Old Sail Parquet statistics can mask mixed NaN/finite values; supplemental pinned physical-output check is still required before treating physical values as independently verified.', 'No dataset/result Parquet was read by this review. Four hashed output files remain remote; diagnostic archive contains no output Parquet.', 'Memory observations are sampled maxima with sequential process reads; kernel cgroup peak includes cache/kernel and differs from requested heap or process PSS.', 'Pinned controller source scope is inherited from retained prelaunch/qualification source audits; this Grust-only review did not fetch/read another repository.'],
        publication_proposal='Keep original diagnostics.tar/server.log privately retained with original SHA/length; publish small exact receipts, complete memory JSONL if desired and a separately reviewed deterministic compressed diagnostic artifact with hash/size and decompression-to-original-SHA proof. Do not rewrite raw logs or stage the389MBlog plus414MBtar redundantly.',
        auditor_sha256=sha(Path(__file__)))
    # Recheck all bound evidence bytes after parsing, archive reads and privacy scan.
    for name,pin in inputs.items():assert bind(REPO/name)==pin
    with (OUT/'receipt.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(report['outcome'],sha(OUT/'receipt.json'))


if __name__=='__main__':main()
