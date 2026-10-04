"""Build the exact unmodified external CLI and retain durable provenance."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

ROOT=Path(sys.argv[1]);REPO=ROOT/'repo';OUTPUT=ROOT/'output';TARGET=ROOT/'target'
SOURCE='b4da56dabe20bba8e29563e06acc5179b2113ce3'

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name: str,value: dict[str,Any]) -> None:
    path=OUTPUT/name;tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as stream:
        stream.write(json.dumps(value,indent=2,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)
    directory=os.open(OUTPUT,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)

def git(*args: str) -> str:
    return subprocess.check_output(['git','-C',str(REPO),*args],text=True).strip()

def identity() -> dict[str,Any]:
    expected=json.loads((ROOT/'source-manifest.json').read_text())
    assert git('rev-parse','HEAD')==SOURCE and not git('status','--porcelain')
    assert subprocess.run(['git','-C',str(REPO),'symbolic-ref','-q','HEAD'],stdout=subprocess.DEVNULL).returncode==1
    assert sha(Path(__file__))==sys.argv[2]
    assert sha(ROOT/'source-manifest.json')==sys.argv[3]
    actual={}
    for name,entry in expected['files'].items():
        path=REPO/name
        assert path.is_file() and not path.is_symlink() and sha(path)==entry['sha256'],name
        actual[name]=sha(path)
    assert set(git('ls-files').splitlines())==set(actual)
    return {'source':SOURCE,'files':actual,'cargo_lock_sha256':sha(REPO/'Cargo.lock'),'helper_sha256':sha(Path(__file__)),'source_manifest_sha256':sha(ROOT/'source-manifest.json')}

def tool(args: list[str]) -> dict[str,Any]:
    p=subprocess.run(args,capture_output=True,text=True,timeout=30)
    return {'command':args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def main() -> int:
    OUTPUT.mkdir(exist_ok=False)
    assert not TARGET.exists(),'target must be fresh'
    exit_code=1
    os.environ.update(CARGO_TARGET_DIR=str(TARGET),CARGO_INCREMENTAL='0',CARGO_BUILD_JOBS='8')
    receipt:dict[str,Any]={'started_utc':datetime.now(timezone.utc).isoformat(),'outcome':'running','purpose':'A1 exact external CLI build; no performance result','source':SOURCE,'cargo_target_dir':str(TARGET),'build_jobs':8}
    save('receipt.json',receipt)
    try:
        receipt['identity_before']=identity()
        receipt['tools']={name:tool(args) for name,args in [('rustc',['rustc','-vV']),('cargo',['cargo','-V']),('cmake',['cmake','--version']),('cxx',['c++','--version'])]}
        assert all(p['returncode']==0 for p in receipt['tools'].values())
        receipt['memory_events_before']=Path('/sys/fs/cgroup/memory.events').read_text()
        receipt['limits']={n:Path('/sys/fs/cgroup',n).read_text().strip() for n in ['memory.max','memory.swap.max','cpu.max','cpuset.cpus.effective','memory.current']}
        command=['cargo','build','--release','--locked','--bin','graphframes','--jobs','8']
        receipt['build_command']=command;save('receipt.json',receipt)
        start=time.monotonic()
        with (OUTPUT/'cargo-build.log').open('w') as log:
            p=subprocess.run(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,timeout=4800)
        receipt['build_returncode']=p.returncode;receipt['build_diagnostic_seconds']=time.monotonic()-start
        save('receipt.json',receipt);p.check_returncode()
        binary=TARGET/'release/graphframes';assert binary.is_file()
        shutil.copy2(binary,OUTPUT/'graphframes-linux-x86_64-b4da56d-release')
        receipt['binary']={'path':str(binary),'retained_path':'graphframes-linux-x86_64-b4da56d-release','bytes':binary.stat().st_size,'sha256':sha(binary)}
        receipt['help']=tool([str(binary),'--help']);receipt['wcc_help']=tool([str(binary),'wcc','--help'])
        assert receipt['help']['returncode']==receipt['wcc_help']['returncode']==0
        receipt['identity_after']=identity();assert receipt['identity_before']==receipt['identity_after']
        receipt['memory_peak_bytes']=int(Path('/sys/fs/cgroup/memory.peak').read_text());receipt['outcome']='passed'
        exit_code=0
    except BaseException as error:
        receipt['outcome']='error';receipt['error']=repr(error)
        traceback.print_exc()
    finally:
        observations=[]
        for name in ['memory.events','memory.peak','memory.current']:
            try:receipt[name.replace('.','_')+'_after']=Path('/sys/fs/cgroup',name).read_text().strip()
            except BaseException as error:observations.append(repr(error))
        try:
            receipt['final_source_identity']=identity()
            if receipt.get('identity_before')!=receipt['final_source_identity']:observations.append('source identity changed')
        except BaseException as error:observations.append(repr(error))
        if observations:
            receipt['final_observation_errors']=observations;receipt['outcome']='error';exit_code=1
        before=dict(line.split() for line in receipt.get('memory_events_before','').splitlines())
        after=dict(line.split() for line in receipt.get('memory_events_after','').splitlines())
        if int(after.get('oom_kill',0))>int(before.get('oom_kill',0)):
            receipt['build_process_oom_kill']=True;receipt['outcome']='error';exit_code=1
        receipt['finished_utc']=datetime.now(timezone.utc).isoformat();save('receipt.json',receipt)
    return exit_code

if __name__=='__main__':
    raise SystemExit(main())
