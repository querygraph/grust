"""Separate six-read/ten-minute ledger using the unchanged reviewed03 observer."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,importlib.util,json,subprocess
ROOT=Path(__file__).resolve().parent
BASE_SHA='b49d83e2ff10b374597ed3d24904cd8ab1688c03081f78dd40b77ace64f7d9cd'
FIRST=datetime.fromisoformat('2026-09-30T22:52:54.404000+00:00')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT/'observe_series.py')==BASE_SHA
spec=importlib.util.spec_from_file_location('reviewed03',ROOT/'observe_series.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def admit(prior,now):
    if len(prior)>=6:raise RuntimeError('followup01 six-read authorization exhausted')
    if now<FIRST:raise RuntimeError('followup01 first read not yet authorized')
    if (ROOT/'followup01-root-stop.json').exists():raise RuntimeError('root stopped followup01')
    if prior:
        previous=prior[-1]
        if previous.get('outcome')!='LIVE_NO_NEW_FAULT_OBSERVED':raise RuntimeError('stop after prior fault/receipt/identity failure')
        if previous.get('returncode')!=0 or previous.get('capture',{}).get('returncode')!=0:raise RuntimeError('prior remote process did not return zero')
        if now<datetime.fromisoformat(previous['local_finished_utc'])+timedelta(seconds=600):raise RuntimeError('wait >=600s after prior return')
    return len(prior)+1


def main():
    now=datetime.now(timezone.utc)
    prior=[json.loads(p.read_text()) for p in sorted(ROOT.glob('followup01-observation-*.json'))]
    ordinal=admit(prior,now)
    first_series=json.loads((ROOT/'series-final.json').read_text())
    assert first_series['read_count']==6 and first_series['last_recorded_workload_state']=='LIVE_NO_NEW_FAULT_OBSERVED'
    initial=json.loads((ROOT/'observation-20260930T220458591359Z.json').read_text())
    latest=prior[-1] if prior else json.loads((ROOT/first_series['observations'][-1]['file']).read_text())
    assert latest['returncode']==latest['capture']['returncode']==0
    request={'reader_sha256':base.READER,'config_sha256':base.CONFIG,'boot_id':base.BOOT,'identity':initial['identity'],'init_start_ticks':15082028,
             'root':initial['volume_inspection']['stdout'].strip(),'previous_offset':latest['observation']['error_scan']['next_offset'],
             'vm_prefix':base.VM_PREFIX,'vm_observer':(ROOT/'vm_observer.py').read_text(),'vm_post':base.VM_POST}
    assert sha(ROOT.parent/'capture_process_identity.py')==base.READER and sha(ROOT.parent/'logging03-compact.json')==base.CONFIG
    output=ROOT/('followup01-observation-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    receipt={'local_started_utc':now.isoformat(),'series':'followup01','ordinal':ordinal,'wrapper_sha256':sha(Path(__file__)),'observer_sha256':BASE_SHA,'vm_observer_sha256':sha(ROOT/'vm_observer.py'),
             'request':{k:v for k,v in request.items() if not k.startswith('vm_')},
             'scope':'One read under separate followup01 authorization. Reviewed VM prefix/reader/observer/postguards and classifier reused unchanged. At most6; >=600s after prior local return. Status/namespace/cgroup and existing sampler/log tails only; no extra PSS/hash/Docker/dmesg/argv/environment/signal/workload operation.'}
    code='import json\nr=json.loads('+repr(json.dumps(request))+')\n'+base.REMOTE
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=code,text=True,capture_output=True,timeout=60)
        receipt.update(returncode=p.returncode,stderr=p.stderr,raw_remote_stdout=p.stdout)
        if p.returncode==0:receipt.update(json.loads(p.stdout))
    except subprocess.TimeoutExpired as e:
        receipt.update(error='local SSH timeout; remote reader termination unproven',stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
    except Exception as e:receipt['error']=repr(e)
    try:receipt['outcome'],receipt['stop_reasons']=base.classify(receipt)
    except Exception as e:receipt.update(outcome='STOP_CAPTURE_FAILURE',stop_reasons=['invalid capture structure'],classification_error=repr(e))
    receipt['local_finished_utc']=datetime.now(timezone.utc).isoformat()
    with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(output),'series':'followup01','ordinal':ordinal,'outcome':receipt['outcome'],'stop_reasons':receipt['stop_reasons']}))

if __name__=='__main__':main()
