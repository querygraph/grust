"""One authorized hash-only recovery for three already mapped logging03 processes."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parent
NOT_BEFORE=datetime.fromisoformat('2026-09-30T22:09:59+00:00')
CID='40128227f08843330ed7a20daa987e042a827c0e51b24c562dfd01a48d5765a5'
BOOT='f5443bfc-c939-491a-a984-b73cc6d1cb20'
EXPECTED='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
READER='0b7746b9a89202723ded4c1816b76a89d4ad0f2190c800cb4dcb84b3d34bc460'
VM=r'''
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,time
request=json.loads(__import__('sys').argv[1]);cid=request['container_id'];expected_boot=request['boot_id']
def ticks(p):return int(p.read_text().rsplit(')',1)[1].split()[19])
def identity(st):return {k:getattr(st,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')}
def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def cg(p):
 value=(p/'cgroup').read_text();assert value.strip()=='0::/docker/'+cid,'cgroup identity differs';return value
r={'started_utc':datetime.now(timezone.utc).isoformat(),'monotonic_started':time.monotonic(),'boot_id_before':boot(),'processes':[]}
try:
 assert r['boot_id_before']==expected_boot,'boot differs'
 init=Path('/proc')/str(request['init_host_pid']);r['init_start_ticks_before']=ticks(init/'stat');assert r['init_start_ticks_before']==request['init_start_ticks'],'init PID reused';r['init_cgroup_before']=cg(init)
 for target in request['targets']:
  pid,start=target['host_pid'],target['start_ticks'];p=Path('/proc')/str(pid);row=dict(target)
  try:
   row['start_ticks_before']=ticks(p/'stat');assert row['start_ticks_before']==start,'PID reused'
   row['cgroup_before']=cg(p);exe=p/'exe';row['executable_target_before']=str(exe.readlink())
   with exe.open('rb') as f:
    row['file_before']=identity(os.fstat(f.fileno()));row['sha256']=hashlib.file_digest(f,'sha256').hexdigest();row['file_after']=identity(os.fstat(f.fileno()))
   row['executable_target_after']=str(exe.readlink());row['current_exe_file_after']=identity(exe.stat());row['start_ticks_after']=ticks(p/'stat');row['cgroup_after']=cg(p)
   assert row['start_ticks_after']==start,'PID reused'
   assert row['executable_target_before']==row['executable_target_after'],'executable target changed'
   assert row['file_before']==row['file_after']==row['current_exe_file_after'],'executable file changed'
   row['matches_runtime561']=row['sha256']==request['expected_binary_sha256']
   row['outcome']='MATCH' if row['matches_runtime561'] else 'HASH_MISMATCH'
  except Exception as e:row.update(outcome='ERROR',error=repr(e))
  r['processes'].append(row)
 r['init_start_ticks_after']=ticks(init/'stat');assert r['init_start_ticks_after']==request['init_start_ticks'],'init PID reused';r['init_cgroup_after']=cg(init)
 r['boot_id_after']=boot();assert r['boot_id_after']==expected_boot,'boot changed'
 r['outcome']='MATCHED_THREE_MAPPED_EXECUTABLES' if len(r['processes'])==3 and all(x['outcome']=='MATCH' for x in r['processes']) else 'PARTIAL_OR_FAILED'
except Exception as e:r.update(outcome='ERROR',error=repr(e))
r.update(finished_utc=datetime.now(timezone.utc).isoformat(),monotonic_finished=time.monotonic());print(json.dumps(r))
'''


def main():
    now=datetime.now(timezone.utc)
    if now<NOT_BEFORE:raise RuntimeError('not authorized before22:09:59 UTC')
    if list(ROOT.glob('hash-recovery-*.json')):raise RuntimeError('exactly one hash-only recovery authorized')
    request={'container_id':CID,'boot_id':BOOT,'init_host_pid':185523,'init_start_ticks':15082028,'expected_binary_sha256':EXPECTED,
             'targets':[{'role':'driver','host_pid':185584,'container_pid':50,'start_ticks':15084870},
                        {'role':'worker_1','host_pid':185701,'container_pid':167,'start_ticks':15085029},
                        {'role':'worker_2','host_pid':185700,'container_pid':166,'start_ticks':15085028}]}
    remote="from pathlib import Path\nimport subprocess,json,hashlib,os\nos.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')\n"
    remote+="assert hashlib.sha256(Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/capture_process_identity.py').read_bytes()).hexdigest()=="+repr(READER)+'\n'
    remote+='command='+repr(['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','/usr/bin/python3','-B','-c',VM,json.dumps(request)])+'\n'
    remote+="""try:
 p=subprocess.run(command,text=True,capture_output=True,timeout=45)
 r={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
except subprocess.TimeoutExpired as e:
 r={'error':'remote Colima timeout; guest reader termination unproven','stdout':e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,'stderr':e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr}
except Exception as e:r={'error':repr(e)}
print(json.dumps(r))
"""
    out=ROOT/('hash-recovery-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    record={'started_utc':now.isoformat(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'request':request,
            'scope':'Exactly one hash-only recovery after retained comm-selector bug. No observer/log/sampler/PSS/dmesg/Docker read, argv/environment access, process signal or workload. Roles bound to prior namespace mapping and startup log, not process-name inference.'}
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'],input=remote,text=True,capture_output=True,timeout=55)
        record.update(returncode=p.returncode,stderr=p.stderr,stdout=p.stdout)
        if p.returncode==0:
            record['capture']=json.loads(p.stdout)
            if record['capture'].get('returncode')==0:record['identity']=json.loads(record['capture']['stdout'])
    except subprocess.TimeoutExpired as e:record.update(error='local SSH timeout; remote termination unproven',stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
    except Exception as e:record['error']=repr(e)
    record['finished_utc']=datetime.now(timezone.utc).isoformat()
    with out.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'output':str(out),'returncode':record.get('returncode'),'error':record.get('error'),'outcome':record.get('identity',{}).get('outcome')}))


if __name__=='__main__':main()
