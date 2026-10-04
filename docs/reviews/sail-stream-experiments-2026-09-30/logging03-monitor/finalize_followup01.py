"""Summarize this closed authorization window locally; never performs a remote read."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
EXPECTED_WRAPPER='72311b1602ba48b7ade006391da9fbbe9c543c06fd21c7225ee352134ca6e18a'
EXPECTED_SOURCE='b49d83e2ff10b374597ed3d24904cd8ab1688c03081f78dd40b77ace64f7d9cd'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())

def main():
    source=ROOT/'observe_series.py';assert sha(source)==EXPECTED_SOURCE
    assert sha(ROOT/'observe_followup01.py')==EXPECTED_WRAPPER
    paths=sorted(ROOT.glob('followup01-observation-*.json'));records=[load(p) for p in paths]
    assert 1<=len(records)<=6
    root_stop=ROOT/'followup01-root-stop.json'
    assert len(records)==6 or records[-1]['outcome']!='LIVE_NO_NEW_FAULT_OBSERVED' or root_stop.exists(),'authorization window is still active'
    initial=load(sorted(ROOT.glob('series-observation-*.json'))[-1])
    previous_end=None;previous_offset=initial['observation']['error_scan']['next_offset'];rows=[]
    for index,(path,record) in enumerate(zip(paths,records),1):
        assert record['ordinal']==index and record['observer_sha256']==EXPECTED_SOURCE
        assert record['wrapper_sha256']==EXPECTED_WRAPPER and record['series']=='followup01'
        assert record['vm_observer_sha256']==sha(ROOT/'vm_observer.py')
        start=datetime.fromisoformat(record['local_started_utc'])
        assert start>=datetime.fromisoformat('2026-09-30T22:52:54.404000+00:00')
        if previous_end is not None:assert start>=previous_end+timedelta(seconds=600)
        assert record['request']['previous_offset']==previous_offset
        if index<len(records):assert record['outcome']=='LIVE_NO_NEW_FAULT_OBSERVED' and record['returncode']==record['capture']['returncode']==0
        previous_end=datetime.fromisoformat(record['local_finished_utc'])
        observation=record.get('observation',{});scan=observation.get('error_scan',{})
        previous_offset=scan.get('next_offset',previous_offset)
        cgroup=observation.get('cgroup',{})
        row={'file':path.name,'sha256':sha(path),'ordinal':index,'started_utc':record['local_started_utc'],'finished_utc':record['local_finished_utc'],'outcome':record['outcome'],'stop_reasons':record['stop_reasons'],'mapped_processes':len(record.get('mapping',{}).get('processes',[])),
             'cgroup_memory_current_bytes':int(cgroup['memory.current']) if isinstance(cgroup.get('memory.current'),str) else None,
             'cgroup_memory_peak_bytes':int(cgroup['memory.peak']) if isinstance(cgroup.get('memory.peak'),str) else None,
             'cgroup_memory_events':dict((key,int(value)) for key,value in (line.split() for line in cgroup['memory.events'].splitlines())) if isinstance(cgroup.get('memory.events'),str) else None,
             'scan_windows':scan.get('windows'),'unscanned_gap_bytes':scan.get('gap_bytes'),'new_fault_matches':scan.get('matches'),'producer_receipt_exists':observation.get('files',{}).get('receipt.json',{}).get('exists')}
        rows.append(row)
    inputs=[source,ROOT/'vm_observer.py',ROOT/'followup01-preparation.json',ROOT/'test_followup01_guards.py',ROOT/'followup01-offline-guards.log',ROOT/'observe_followup01.py',ROOT/'series-final.json',ROOT/'legacy_logging02_observe.py',ROOT/'identity-summary.json',Path(__file__)]+paths+sorted(ROOT.glob('followup01-command*.log'))+([root_stop] if root_stop.exists() else [])
    before={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in inputs}
    result={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'AUTHORIZED_OBSERVATION_WINDOW_CLOSED','read_count':len(records),'maximum_authorized':6,'stop_reason':'six-read authorization exhausted' if len(records)==6 and records[-1]['outcome']=='LIVE_NO_NEW_FAULT_OBSERVED' else ('root stop' if root_stop.exists() else records[-1]['outcome']),
            'last_recorded_workload_state':records[-1]['outcome'],'observations':rows,'gap_bytes_across_new_scan_intervals':sum(x['unscanned_gap_bytes'] or 0 for x in rows),'input_files':before,
            'limits':['This closes only the authorized monitoring series, not the benchmark/workload. No whole-run success, failure, memory peak, performance ratio or causal conclusion follows from these point reads.', 'Each read used original sampler tails plus status/namespace/cgroup metadata and bounded new log windows; no additional PSS scan, executable hashing, Docker query, dmesg, signal or workload operation.', 'Initial identity-selector defect and authorized exact-PID hash recovery remain separately retained. Initial DEBUG preface-close is not a new terminal fault; new-window gaps/truncation prevent an absence-of-all-errors claim.', 'Same PID/start/namespace/cgroup evidence is sampled identity, not continuous tracing or continuous executable-byte attestation. Zero guest/cgroup OOM counters do not rule out host paging or other memory-related mechanisms.', 'Every prior read returned zero before the next started; starts were at least600s after the previous local return. All observations and command outputs remain unchanged. Further remote monitoring requires new authorization.']}
    with (ROOT/'followup01-final.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    assert all(sha(ROOT/name)==value['sha256'] for name,value in before.items())
    print(json.dumps({'output':str(ROOT/'followup01-final.json'),'sha256':sha(ROOT/'followup01-final.json'),'read_count':len(records),'stop_reason':result['stop_reason'],'last_recorded_workload_state':result['last_recorded_workload_state']}))

if __name__=='__main__':main()
