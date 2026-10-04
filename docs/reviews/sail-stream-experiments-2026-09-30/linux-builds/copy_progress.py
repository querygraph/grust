"""Read-only bounded copy progress sample; metadata and process counters only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

sample = r'''
from datetime import datetime, timezone
import json, os, pathlib, time

def tree(root):
    result = dict(files=0, directories=0, logical_bytes=0, allocated_bytes=0, newest_mtime_ns=0)
    for parent, dirs, files in os.walk(root):
        result['directories'] += len(dirs)
        for name in files:
            try:
                info = (pathlib.Path(parent) / name).lstat()
            except FileNotFoundError:
                continue
            result['files'] += 1
            result['logical_bytes'] += info.st_size
            result['allocated_bytes'] += info.st_blocks * 512
            result['newest_mtime_ns'] = max(result['newest_mtime_ns'], info.st_mtime_ns)
    return result
record = dict(utc=datetime.now(timezone.utc).isoformat(), scope='metadata and cp process counters; no file content reads')
started=time.monotonic()
record['source']=tree('/targets/graph-nuts-ffcfbd569/target-host')
record['destination']=tree('/targets/sail-stream-2894a962076d/target-host')
record['cp_processes']=[]
for p in pathlib.Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        if (p/'comm').read_text().strip() != 'cp': continue
        fields=(p/'stat').read_text().rsplit(')',1)[1].split()
        item=dict(pid=int(p.name),state=fields[0],elapsed_seconds=float(pathlib.Path('/proc/uptime').read_text().split()[0])-int(fields[19])/os.sysconf('SC_CLK_TCK'))
        try: item['io']={k:int(v.strip()) for k,v in (line.split(':') for line in (p/'io').read_text().splitlines())}
        except PermissionError: item['io']='permission denied'
        item['open_target_files']=[]
        for fd in (p/'fd').iterdir():
            try:
                value=os.readlink(fd)
                if '/target-host/' in value: item['open_target_files'].append(value)
            except (OSError,PermissionError): pass
        record['cp_processes'].append(item)
    except (FileNotFoundError,ProcessLookupError): pass
record['sample_seconds']=time.monotonic()-started
print(json.dumps(record))
'''
remote = "import subprocess\ncommand=" + repr(['/usr/local/bin/docker','--context','colima-sail-gate','exec','sail-stream-build289','python3','-c',sample]) + "\nsubprocess.run(command,check=True)\n"
result=subprocess.run(['ssh','morrobay','PATH=/usr/local/bin:/usr/bin:/bin python3 -'],input=remote,text=True,capture_output=True,check=True)
record=json.loads(result.stdout)
root=Path(__file__).resolve().parent/'integration289'/'copy-progress'
root.mkdir(exist_ok=True)
out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(path=str(out),**record),indent=2))
