"""Bounded read-only compiler/process and cgroup sample; no process arguments."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

sample = r'''
from datetime import datetime, timezone
import json, os, pathlib, shutil, time
names={'rustc','cargo','cc','c++','gcc','g++','clang','clang++','ld','ld.lld','lld','collect2','rust-lld'}
hz=os.sysconf('SC_CLK_TCK')
def snapshot():
    processes=[]
    uptime=float(pathlib.Path('/proc/uptime').read_text().split()[0])
    for path in pathlib.Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            comm=(path/'comm').read_text().strip()
            if comm not in names: continue
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            processes.append(dict(pid=int(path.name),comm=comm,state=fields[0],
                parent_pid=int(fields[1]),elapsed_seconds=uptime-int(fields[19])/hz,
                cpu_seconds=(int(fields[11])+int(fields[12]))/hz,threads=int(fields[17])))
        except (FileNotFoundError,ProcessLookupError,PermissionError): pass
    cgroup={}
    for name in ('cpu.stat','cpu.max','memory.current','memory.peak','memory.events','memory.max'):
        path=pathlib.Path('/sys/fs/cgroup')/name
        cgroup[name]=path.read_text().strip() if path.exists() else None
    return dict(utc=datetime.now(timezone.utc).isoformat(),processes=processes,
                cgroup=cgroup,free_bytes=shutil.disk_usage('/targets').free)
start=time.monotonic()
before=snapshot()
time.sleep(5)
after=snapshot()
interval=time.monotonic()-start
old={p['pid']:p for p in before['processes']}
for p in after['processes']:
    if p['pid'] in old and p['comm']==old[p['pid']]['comm']:
        p['cpu_percent_over_sample']=100*(p['cpu_seconds']-old[p['pid']]['cpu_seconds'])/interval
print(json.dumps(dict(scope='compiler progress only; no arguments or file contents',sample_seconds=interval,before=before,after=after)))
'''
remote='import subprocess\ncommand='+repr(['/usr/local/bin/docker','--context','colima-sail-gate','exec','sail-stream-build289','python3','-c',sample])+'\nsubprocess.run(command,check=True)\n'
result=subprocess.run(['ssh','morrobay','PATH=/usr/local/bin:/usr/bin:/bin python3 -'],input=remote,text=True,capture_output=True,check=True)
record=json.loads(result.stdout)
root=Path(__file__).resolve().parent/'integration289'/'host-progress'
root.mkdir(exist_ok=True)
p=root/('compiler-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
p.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(path=str(p),**record),indent=2))
