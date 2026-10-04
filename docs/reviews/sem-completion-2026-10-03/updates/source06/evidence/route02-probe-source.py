import socket,os,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
time.sleep(float(sys.argv[2]))
r={'observed_utc':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'executable':sys.executable,'endpoint':['192.168.4.61',49190]}
try:
    with socket.create_connection(('192.168.4.61',49190),timeout=3) as s:
        s.sendall(b'GET /minio/health/ready HTTP/1.0\r\nHost: 192.168.4.61\r\n\r\n')
        r['response_status']=s.recv(256).split(b'\r\n',1)[0].decode('ascii')
    r['connected']=True
except OSError as e:
    r.update(connected=False,errno=e.errno,error=str(e))
Path(sys.argv[1]).write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r))
