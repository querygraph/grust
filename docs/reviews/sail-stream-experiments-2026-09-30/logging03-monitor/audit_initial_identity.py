"""Local-only binding of the initial03 observation and authorized hash recovery."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
CID='40128227f08843330ed7a20daa987e042a827c0e51b24c562dfd01a48d5765a5'
BOOT='f5443bfc-c939-491a-a984-b73cc6d1cb20'
EXPECTED='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())

def main():
    initial_path=ROOT/'observation-20260930T220458591359Z.json'
    recovery_path=ROOT/'hash-recovery-20260930T221010268032Z.json'
    initial,recovery=load(initial_path),load(recovery_path)
    assert initial['returncode']==initial['capture']['returncode']==recovery['returncode']==recovery['capture']['returncode']==0
    assert initial['container_id']==CID and initial['state']['Running'] is True
    assert initial['observation']['boot_id']==BOOT
    assert initial['observer_sha256']==sha(ROOT/'initial_observation.py')
    assert initial['vm_observer_sha256']==sha(ROOT/'vm_observer.py')
    assert recovery['source_sha256']==sha(ROOT/'hash_recovery.py')
    assert datetime.fromisoformat(recovery['started_utc'])>=datetime.fromisoformat('2026-09-30T22:09:59+00:00')
    mapped={x['host_pid']:x for x in initial['mapping']['processes']}
    capture=recovery['identity']
    assert capture['outcome']=='MATCHED_THREE_MAPPED_EXECUTABLES'
    assert capture['boot_id_before']==capture['boot_id_after']==BOOT
    assert capture['init_start_ticks_before']==capture['init_start_ticks_after']==15082028
    assert initial['executable_identity']['init_start_ticks_before']==initial['executable_identity']['init_start_ticks_after']==15082028
    roles=[]
    for item in capture['processes']:
        previous=mapped[item['host_pid']]
        assert previous['start_ticks']==item['start_ticks_before']==item['start_ticks_after']==item['start_ticks']
        assert int(previous['status']['NSpid'].split()[-1])==item['container_pid']
        assert previous['cgroup']==item['cgroup_before']==item['cgroup_after']=='0::/docker/'+CID+'\n'
        assert item['sha256']==EXPECTED and item['matches_runtime561'] is True
        assert item['executable_target_before']==item['executable_target_after']
        assert item['file_before']==item['file_after']==item['current_exe_file_after']
        roles.append({k:item[k] for k in ('role','host_pid','container_pid','start_ticks','executable_target_before','sha256')})
    assert len(roles)==3
    starts=initial['executable_identity']['worker_startup_excerpt']
    for worker,pid in ((1,167),(2,166)):
        assert any(re.search(r'extension process worker '+str(worker)+r': pid=Some\('+str(pid)+r'\), driver_pid=50',x) for x in starts)
    assert all(mapped[p]['status']['PPid']=='185584' for p in (185700,185701))
    before={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in ROOT.iterdir() if p.is_file()}
    result={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'INITIAL03_PID_NAMESPACE_AND_EXECUTABLE_IDENTITY_CONFIRMED',
            'container_id':CID,'boot_id':BOOT,'init_host_pid':185523,'init_start_ticks':15082028,'roles':roles,
            'initial_observation':{'file':initial_path.name,'started_utc':initial['local_started_utc'],'finished_utc':initial['local_finished_utc'],'cgroup':initial['observation']['cgroup'],'existing_sampler_tail':{k:v for k,v in initial['observation']['files']['memory-samples.jsonl'].items() if k!='tail_utf8'},'error_scan':initial['observation']['error_scan']},
            'hash_recovery':{'file':recovery_path.name,'started_utc':recovery['started_utc'],'finished_utc':recovery['finished_utc']},
            'retained_initial_selector_error':{'producer_reported_sail_process_count':initial['executable_identity']['mapped_sail_process_count'],'actual_named_mapped_candidates':3,'actual_comm':'sail-linux-x86_','cause':'Initial executable selector required Name == sail; it skipped the three correctly mapped differently named runtime processes. Initial source and receipt remain unchanged. One explicitly authorized exact-PID recovery supplies the hashes.'},
            'limits':['Two remote read operations only: initial mapping/original-sampler/log observation, then one exact-PID hash-only recovery. No repeating monitor loop or additional reads authorized/performed.', 'Startup DEBUG connection-closed-before-preface line is retained; it is not sufficient to classify a workload stream fault.', 'Roles use startup log namespace PID plus captured NSpid/host PID/start/cgroup mapping. Identity is point-in-time, not continuous process tracing or full task success.', 'Original sampler tail is bounded/truncated; this is not a new PSS scan, complete progress record, benchmark result or full-run memory guarantee.', 'No signals, container/workload changes, process arguments/environment, dmesg or other kernel-log read.'],
            'evidence_files':before}
    with (ROOT/'identity-audit.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    assert all(sha(ROOT/n)==v['sha256'] for n,v in before.items())
    print(json.dumps({'outcome':result['outcome'],'receipt':str(ROOT/'identity-audit.json'),'sha256':sha(ROOT/'identity-audit.json')}))

if __name__=='__main__':main()
