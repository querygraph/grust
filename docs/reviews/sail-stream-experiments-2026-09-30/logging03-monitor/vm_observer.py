
import os,re
options=json.loads(sys.argv[2])
root=Path(options['root'])/'sail-stream-experiments-20260930/logging03-compact/cells/stream-log03-compact-r1-scale24-pecan-sssp-delta_star'
result={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'uptime':Path('/proc/uptime').read_text().strip(),'monotonic':time.monotonic(),'cpu_stat':Path('/proc/stat').read_text().splitlines()[0]}
init=options['identity']['init_host_pid'];cgtext=(Path('/proc')/str(init)/'cgroup').read_text();assert options['identity']['container_id'] in cgtext
cgpath=cgtext.split('::',1)[1].strip();cg=Path('/sys/fs/cgroup')/cgpath.lstrip('/')
result['cgroup_path']=cgpath;result['cgroup']={}
for name in ['memory.current','memory.peak','memory.max','memory.events','memory.stat','cpu.stat','cpuset.cpus.effective','io.stat']:
 p=cg/name
 try:result['cgroup'][name]=p.read_text()
 except OSError as e:result['cgroup'][name]={'error':repr(e)}
result['files']={}
for name,limit in [('memory-samples.jsonl',16384),('server.log',32768),('receipt.json',65536),('server-settings.json',16384)]:
 p=root/name
 if not p.exists():result['files'][name]={'exists':False};continue
 st=p.stat();offset=max(0,st.st_size-limit)
 with p.open('rb') as f:f.seek(offset);data=f.read(limit)
 result['files'][name]={'exists':True,'bytes_at_start':st.st_size,'mtime_ns':st.st_mtime_ns,'offset':offset,'tail_utf8':data.decode(errors='replace')}
 if name=='server.log':
  previous=min(options['previous_offset'],st.st_size);end=st.st_size;windows=[(previous,min(end,previous+2*1024**2))]
  if end-windows[0][1]>0:windows.append((max(windows[0][1],end-2*1024**2),end))
  errors=[]
  with p.open('rb') as f:
   for start,stop in windows:
    f.seek(start);chunk=f.read(stop-start)
    pos=start
    for line in chunk.splitlines(keepends=True):
     if line.startswith(b'[') and re.search(rb'(?i)(?<![a-z])(?:ERROR|panic|panicked|OutOfMemory|failed|stream_error)(?![a-z])',line):
      if len(errors)<20:errors.append({'offset':pos,'line_utf8':line[:4096].decode(errors='replace'),'truncated':len(line)>4096})
     pos+=len(line)
  result['error_scan']={'windows':windows,'gap_bytes':max(0,end-previous-sum(b-a for a,b in windows)),'matches':errors,'next_offset':end,'scope':'First matches within bounded scanned windows only; full server log remains authoritative.'}
result['volume_free_bytes']=__import__('shutil').disk_usage(options['root']).free
print(json.dumps(result))
