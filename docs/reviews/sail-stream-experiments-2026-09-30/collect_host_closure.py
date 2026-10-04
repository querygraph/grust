#!/usr/bin/env python3
"""One bounded read of host pressure and guest kernel evidence after a cell closes.

No signal, container launch, process argv/environment read or workload operation.
Full SSH/kernel text stays private; the public receipt contains only OOM records
and the explicitly selected host pressure/process-name snapshots.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
HOST_ROOT = '/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930'
PRIVATE = Path('/private/tmp/sail-review-private-evidence')
HOST_SNAPSHOTS = ('physical_memory', 'swap', 'vm_stat', 'processes', 'docker_running')
OOM = re.compile(r'oom-kill:|Out of memory:|Memory cgroup out of memory:|Killed process|oom_reaper:')
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
VM_CODE = '''
from pathlib import Path
import subprocess,json
from datetime import datetime,timezone
r={'started_utc':datetime.now(timezone.utc).isoformat()}
try:
 r['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 r['uptime']=Path('/proc/uptime').read_text().strip()
 p=subprocess.run(['/usr/bin/dmesg'],text=True,capture_output=True,timeout=15)
 r.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
 r['boot_id_after']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
except subprocess.TimeoutExpired as e:
 r.update(error_type='TimeoutExpired',stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,
          stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr)
except Exception as e:
 r.update(error_type=type(e).__name__,error=str(e))
r['finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(r))
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def as_bytes(value):
    return value if isinstance(value, bytes) else (value or '').encode()


def metadata(data):
    raw = as_bytes(data)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def parse_object(text):
    def reject(value):
        raise ValueError('nonfinite JSON')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    value = json.loads(text, parse_constant=reject, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError('expected JSON object')
    return value


def build_remote(config_name, pin):
    remote = '''
from datetime import datetime,timezone
from pathlib import Path
import subprocess,json,hashlib,os
os.environ['PATH']='/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')
'''
    remote += 'config=Path(' + repr(HOST_ROOT + '/' + config_name) + ')\n'
    remote += 'assert hashlib.sha256(config.read_bytes()).hexdigest()==' + repr(pin) + '\n'
    remote += 'vm_code=' + repr(VM_CODE) + '\n'
    remote += '''
r={'started_utc':datetime.now(timezone.utc).isoformat(),'snapshots':{}}
commands=[('physical_memory',['/usr/sbin/sysctl','hw.memsize'],3),
 ('swap',['/usr/sbin/sysctl','vm.swapusage'],3),('vm_stat',['/usr/bin/vm_stat'],3),
 ('processes',['/bin/ps','-axo','pid=,ppid=,rss=,comm='],5),
 ('docker_running',['/usr/local/bin/docker','--context','colima-sail-gate','ps','--no-trunc','--format','{{.ID}} {{.Names}}'],5),
 ('guest',['/usr/local/bin/colima','--profile','sail-gate','ssh','--','sudo','-n','/usr/bin/python3','-B','-c',vm_code],20)]
for name,command,timeout in commands:
 try:
  p=subprocess.run(command,text=True,capture_output=True,timeout=timeout)
  r['snapshots'][name]={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except subprocess.TimeoutExpired as e:
  r['snapshots'][name]={'error_type':'TimeoutExpired','stdout':e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,'stderr':e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr}
 except Exception as e:
  r['snapshots'][name]={'error_type':type(e).__name__,'error':str(e)}
r['finished_utc']=datetime.now(timezone.utc).isoformat();print(json.dumps(r))
'''
    return remote


def successful(capture):
    return type(capture.get('returncode')) is int and capture['returncode'] == 0 and not capture.get('error_type')


def public_capture(capture, include_stdout=False):
    if not isinstance(capture, dict):
        raise ValueError('capture must be an object')
    result = {key: capture[key] for key in ('returncode', 'error_type') if key in capture}
    for name in ('stdout', 'stderr'):
        value = capture.get(name) or ''
        if not isinstance(value, str):
            raise ValueError('capture text must be a string')
        result[name + '_metadata'] = metadata(value)
    if include_stdout:
        result['stdout'] = capture.get('stdout') or ''
    return result


def interpret(record, raw):
    host = parse_object(raw)
    snapshots = host['snapshots']
    if not isinstance(snapshots, dict):
        raise ValueError('snapshots must be an object')
    record['host'] = {key: host[key] for key in ('started_utc', 'finished_utc')}
    record['host']['snapshots'] = {name: public_capture(snapshots[name], True) for name in HOST_SNAPSHOTS}
    guest = snapshots['guest']
    record['guest_command'] = public_capture(guest)
    complete = all(successful(snapshots[name]) for name in HOST_SNAPSHOTS) and successful(guest)
    if successful(guest):
        value = parse_object(guest['stdout'])
        kernel = value.get('stdout') or ''
        if not isinstance(kernel, str):
            raise ValueError('kernel stdout must be text')
        public = public_capture(value)
        for key in ('started_utc', 'finished_utc', 'boot_id', 'boot_id_after', 'uptime'):
            if key in value:
                public[key] = value[key]
        same_boot = (isinstance(value.get('boot_id'), str) and BOOT_ID.fullmatch(value['boot_id']) is not None
                     and value['boot_id'] == value.get('boot_id_after'))
        public.update(boot_identity_stable=same_boot,
            full_dmesg_decoded_text_sha256=sha(kernel.encode()), full_dmesg_decoded_text_bytes=len(kernel.encode()),
            oom_lines=[dict(line_number=i, text=line) for i, line in enumerate(kernel.splitlines(), 1) if OOM.search(line)],
            selection='Exact selected lines of decoded dmesg stdout; full SSH bytes retained privately. No absence-of-OOM inference if a read failed or boot differs. Not a per-cell time filter or victim-to-worker attribution.')
        record['guest'] = public
        complete = complete and successful(value) and same_boot
    record['outcome'] = 'CAPTURED' if complete else 'PARTIAL_CAPTURE'


def collect(case, output):
    if output.exists():
        raise FileExistsError('receipt already exists')
    record = dict(started_utc=utc(), case=case, outcome='FAILED',
        scope='Post-cell read only; caller must establish cell termination. Mac host paging counters and guest boot/kernel records. Counters are not per-cell physical I/O or causal attribution.',
        timeout_seconds={'local_ssh':55,'remote_commands_sum':39,'nested_dmesg':15},
        privacy='Full stdout/stderr and exception detail stay in a private directory; public stderr contains only size/hash. Host ps selects comm, never args/environment.')
    private = None
    raw = stderr = b''
    exception = None
    try:
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        private = Path(tempfile.mkdtemp(prefix='closure-' + case + '-', dir=PRIVATE))
        record['private_directory'] = str(private)
        record['collector_sha256'] = sha(Path(__file__).read_bytes())
        config = ROOT / (case + '.json')
        pin = sha(config.read_bytes())
        record['config_sha256'] = pin
        remote = build_remote(config.name, pin)
        record['remote_source'] = remote
        # The destination and remote shell command are constant; data/code go on stdin.
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            'morrobay', 'python3 -B -'], input=remote.encode(), capture_output=True, timeout=55)
        raw, stderr = as_bytes(result.stdout), as_bytes(result.stderr)
        record['returncode'] = result.returncode
        if result.returncode == 0:
            interpret(record, raw)
        else:
            record['error'] = 'SSH/remote reader returned nonzero; inspect private raw evidence'
    except subprocess.TimeoutExpired as error:
        raw, stderr = as_bytes(error.stdout), as_bytes(error.stderr)
        record.update(error_type='TimeoutExpired', error='Local SSH timeout; remote reader termination unproven')
        exception = str(error)
    except Exception as error:
        record.update(outcome='FAILED', error_type=type(error).__name__,
            error='Collector launch, configuration, capture or parsing failed; inspect private raw evidence')
        exception = str(error)
    finally:
        record.update(private_stdout=metadata(raw), private_stderr=metadata(stderr))
        record['private_retention_errors'] = []
        if private is not None:
            for name, data in [('ssh.stdout', raw), ('ssh.stderr', stderr),
                               ('exception.txt', as_bytes(exception))]:
                try:
                    with (private/name).open('xb') as stream:
                        stream.write(data)
                except OSError as error:
                    record['private_retention_errors'].append({'file':name,'error_type':type(error).__name__})
        else:
            record['private_retention_errors'].append({'error':'private directory unavailable'})
        if record['private_retention_errors']:
            record['outcome'] = 'FAILED'
        record['finished_utc'] = utc()
        # A writable output path is required; filesystem failure here cannot be receipted there.
        with output.open('x') as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
            stream.write('\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('logging02', 'logging03-compact'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = collect(args.case, args.output)
    print(json.dumps(dict(output=str(args.output), outcome=record['outcome'],
                          returncode=record.get('returncode'), error=record.get('error'))))
    return 0 if record['outcome'] == 'CAPTURED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
