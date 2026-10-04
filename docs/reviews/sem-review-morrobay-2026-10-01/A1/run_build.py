"""Own one admitted A1 build, with durable failures and certain closure."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,importlib.util,io,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from typing import Any
BASE=Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/A1')
GUEST='/targets/sem-review-20261001/A1-run01'
IMAGE='sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
MATRIX=Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/harness/run_matrix.py')
DOCKER=['docker','--context','colima-sail-gate']
PYTHON='/targets/graph-nuts-ffcfbd569/venv/bin/python'
STAGE="""import pathlib,tarfile,sys,shutil,json,subprocess,hashlib
root=pathlib.Path(sys.argv[1]);assert not root.exists()
mem=pathlib.Path('/proc/meminfo').read_text();available=int(next(x.split()[1] for x in mem.splitlines() if x.startswith('MemAvailable:')))*1024
free=shutil.disk_usage('/targets').free;assert available>=40*2**30 and free>=40*2**30
root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.issym() and not m.islnk()
  p=pathlib.Path(m.name);assert not p.is_absolute() and '..' not in p.parts
  out=root/p;out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as stream:shutil.copyfileobj(t.extractfile(m),stream)
manifest=json.loads((root/'source-manifest.json').read_text())
bundle=root/'graphframes-rs-b4da56d.bundle';assert hashlib.sha256(bundle.read_bytes()).hexdigest()==manifest['bundle_sha256']
subprocess.run(['git','clone',str(bundle),str(root/'repo')],check=True)
subprocess.run(['git','-C',str(root/'repo'),'checkout','--detach',manifest['source']],check=True)
print(json.dumps({'available_memory_bytes':available,'volume_free_bytes':free,'source':manifest['source'],'root':str(root)}))
"""

def sha(p: Path) -> str:return hashlib.sha256(p.read_bytes()).hexdigest()

def save(path: Path,value: dict[str,Any]) -> None:
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps({'recorded_utc':datetime.now(timezone.utc).isoformat(),**value},indent=2,sort_keys=True)+'\n');tmp.replace(path)

def idle() -> None:
    assert not subprocess.check_output(DOCKER+['ps','-q'],text=True,timeout=30).strip(),'gate busy'

def main() -> int:
    host=BASE/'host-run01';host.mkdir(exist_ok=False)
    lock=BASE.parent/'gate.lock';lock.mkdir(exist_ok=False)
    save(lock/'owner.json',{'pid':os.getpid(),'item':'A1','guest':GUEST,'host':str(host)})
    final:dict[str,Any]={'outcome':'error','item':'A1','certain_container_closure':False,'lock_retained':True}
    save(host/'result.json',final)
    try:
        idle();assert sha(MATRIX)=='21d12c888caabb59acece11a2ee27837974c1f34b08cc499600e305d6341e1a0'
        files=[BASE/'support'/n for n in ['graphframes-rs-b4da56d.bundle','source-manifest.json','build_graphframes.py']]
        save(host/'support-manifest.json',{'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},'wrapper_sha256':sha(Path(__file__))})
        payload=io.BytesIO()
        with tarfile.open(fileobj=payload,mode='w') as t:
            for p in files:t.add(p,arcname=p.name,recursive=False)
        command=DOCKER+['run','--rm','-i','--name','sem-review-a1-stage-run01','--read-only','--network','none','--cpus','1','--memory','512m','--memory-swap','512m','--pids-limit','32','--mount','type=volume,source=sail-extension-targets,target=/targets','--entrypoint',PYTHON,IMAGE,'-I','-B','-c',STAGE,GUEST]
        stage=subprocess.run(command,input=payload.getvalue(),capture_output=True,timeout=120)
        save(host/'stage.json',{'command':command,'returncode':stage.returncode,'stdout':stage.stdout.decode(),'stderr':stage.stderr.decode()});stage.check_returncode();idle()
        sys.path.insert(0,str(MATRIX.parent));spec=importlib.util.spec_from_file_location('pinned_matrix',MATRIX);assert spec and spec.loader
        matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
        config={'docker_context':'colima-sail-gate','image':IMAGE,'target_volume':'sail-extension-targets','container_python':PYTHON,'container_repo':GUEST+'/repo','environment':{},'limits':{'cpus':16,'cpuset_cpus':'0-15','memory_gib':32}}
        command=['-I','-B',GUEST+'/build_graphframes.py',GUEST]
        save(host/'configuration.json',{'config':config,'command':command,'outer_timeout_seconds':5400})
        record=matrix.run_container(config,'sem-review-a1-build-run01',command,host/'container',IMAGE,5400,{'results':GUEST+'/output'})
        save(host/'container-record.json',record)
        state=(record.get('inspect') or {}).get('state',{})
        certain=bool(state.get('Running') is False and state.get('ExitCode') is not None and record.get('remove',{}).get('returncode')==0 and not record.get('transport_errors'))
        producer_path=host/'container/results/receipt.json';producer=json.loads(producer_path.read_text()) if producer_path.exists() else None
        passed=bool(certain and record.get('attach_returncode')==0 and state.get('ExitCode')==0 and not state.get('OOMKilled') and not record.get('outer_timeout') and producer and producer.get('outcome')=='passed')
        final.update(outcome='passed' if passed else 'not_passed',certain_container_closure=certain,container_state=state,producer_outcome=producer.get('outcome') if producer else None,outer_timeout=record.get('outer_timeout'),transport_errors=record.get('transport_errors'))
        if passed:
            binary=host/'container/results'/producer['binary']['retained_path'];assert sha(binary)==producer['binary']['sha256'];final['binary_sha256']=sha(binary)
        if certain:
            (lock/'owner.json').unlink();lock.rmdir();final['lock_retained']=False
        idle();return 0 if passed else 1
    except BaseException as error:
        final['error']=repr(error);raise
    finally:save(host/'result.json',final)

if __name__=='__main__':raise SystemExit(main())
