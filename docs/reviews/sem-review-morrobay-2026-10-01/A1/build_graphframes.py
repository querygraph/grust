"""Build the exact unmodified external CLI and retain durable provenance."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

ROOT=Path(sys.argv[1]);REPO=ROOT/'repo';OUTPUT=ROOT/'output';TARGET=ROOT/'target'
SOURCE='b4da56dabe20bba8e29563e06acc5179b2113ce3'

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name: str,value: dict[str,Any]) -> None:
    path=OUTPUT/name;tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');tmp.replace(path)

def git(*args: str) -> str:
    return subprocess.check_output(['git','-C',str(REPO),*args],text=True).strip()

def identity() -> dict[str,Any]:
    expected=json.loads((ROOT/'source-manifest.json').read_text())
    assert git('rev-parse','HEAD')==SOURCE and not git('status','--porcelain')
    actual={}
    for name,entry in expected['files'].items():
        path=REPO/name
        assert path.is_file() and not path.is_symlink() and sha(path)==entry['sha256'],name
        actual[name]=sha(path)
    assert set(git('ls-files').splitlines())==set(actual)
    return {'source':SOURCE,'files':actual,'cargo_lock_sha256':sha(REPO/'Cargo.lock')}

def tool(args: list[str]) -> dict[str,Any]:
    p=subprocess.run(args,capture_output=True,text=True,timeout=30)
    return {'command':args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def main() -> int:
    OUTPUT.mkdir(exist_ok=False)
    os.environ.update(CARGO_TARGET_DIR=str(TARGET),CARGO_INCREMENTAL='0',CARGO_BUILD_JOBS='8')
    receipt:dict[str,Any]={'started_utc':datetime.now(timezone.utc).isoformat(),'outcome':'running','purpose':'A1 exact external CLI build; no performance result','source':SOURCE,'cargo_target_dir':str(TARGET),'build_jobs':8}
    save('receipt.json',receipt)
    try:
        receipt['identity_before']=identity()
        receipt['tools']={name:tool(args) for name,args in [('rustc',['rustc','-vV']),('cargo',['cargo','-V']),('cmake',['cmake','--version']),('cxx',['c++','--version'])]}
        assert all(p['returncode']==0 for p in receipt['tools'].values())
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
        return 0
    except BaseException as error:
        receipt['outcome']='error';receipt['error']=repr(error)
        raise
    finally:
        receipt['finished_utc']=datetime.now(timezone.utc).isoformat();save('receipt.json',receipt)

if __name__=='__main__':
    raise SystemExit(main())
