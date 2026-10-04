"""Read one Docker cell's host/container PID mapping on Morrobay.

Supplemental diagnostic only: does not mutate or signal the cell. Records no
process arguments or environment. The original benchmark sampler stays pinned.
Run on the Docker client host while the cell is running, with a fresh output.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


VM_READER = r'''
import json,sys,time
from pathlib import Path
identity = json.loads(sys.argv[1])
fields = {'Name', 'State', 'Tgid', 'Pid', 'PPid', 'NSpid', 'VmRSS', 'VmSize',
          'RssAnon', 'RssFile', 'VmSwap', 'Threads', 'FDSize'}

def start_ticks(stat):
    return int(stat.rsplit(')', 1)[1].split()[19])

def read_process(pid):
    root = Path('/proc') / str(pid)
    try:
        before = (root / 'stat').read_text()
        cgroup = (root / 'cgroup').read_text()
        if identity['container_id'] not in cgroup:
            return {'host_pid': pid, 'error': 'container cgroup identity differs'}
        status = {}
        for line in (root / 'status').read_text().splitlines():
            name, value = line.split(':', 1)
            if name in fields:
                status[name] = value.strip()
        after = (root / 'stat').read_text()
        if start_ticks(before) != start_ticks(after):
            return {'host_pid': pid, 'error': 'PID start time changed during capture'}
        return {'host_pid': pid, 'start_ticks': start_ticks(before),
                'cgroup': cgroup, 'status': status}
    except (OSError, ValueError, IndexError) as error:
        return {'host_pid': pid, 'error': repr(error)}

started = time.monotonic()
rows = [read_process(pid) for pid in identity['host_pids']]
print(json.dumps({'monotonic_started': started, 'monotonic_finished': time.monotonic(),
                  'clock_ticks_per_second': __import__('os').sysconf('SC_CLK_TCK'),
                  'processes': rows}))
'''


def utc():
    return datetime.now(timezone.utc).isoformat()


def run(command):
    completed = subprocess.run(command, text=True, capture_output=True, timeout=60)
    return dict(command=command, returncode=completed.returncode,
                stdout=completed.stdout, stderr=completed.stderr)


def parse_top(value):
    lines = value.splitlines()
    if not lines or lines[0].split() != ['PID', 'PPID', 'COMMAND']:
        raise ValueError('unexpected docker top columns')
    rows = []
    for line in lines[1:]:
        pid, parent, name = line.split(None, 2)
        rows.append(dict(host_pid=int(pid), parent_host_pid=int(parent), name=name))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('container')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'sail-[a-zA-Z0-9_.-]+', args.container):
        parser.error('only an explicitly named Sail experiment container is accepted')
    # Reserve before issuing any commands; never overwrite earlier evidence.
    with args.output.open('x') as output:
        receipt = dict(started_utc=utc(), container_name=args.container,
                       scope='read-only process identity; no arguments or environment')
        try:
            os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + os.environ.get('PATH', '')
            docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
            inspection = run(docker + ['inspect', '--format',
                '{{json .Id}} {{json .State.Pid}} {{json .State.Running}}', args.container])
            receipt['inspect'] = inspection
            if inspection['returncode']:
                raise RuntimeError('container inspection failed')
            container_id, initial_pid, running = inspection['stdout'].split()
            container_id = json.loads(container_id)
            if not re.fullmatch('[a-f0-9]{64}', container_id) or running != 'true':
                raise ValueError('container is not running with a complete ID')
            top = run(docker + ['top', container_id, '-eo', 'pid,ppid,comm'])
            receipt['top'] = top
            if top['returncode']:
                raise RuntimeError('container process listing failed')
            rows = parse_top(top['stdout'])
            identity = dict(container_id=container_id, init_host_pid=int(initial_pid),
                            host_pids=[row['host_pid'] for row in rows])
            receipt['identity'] = identity
            capture = run(['/usr/local/bin/colima', '--profile', 'sail-gate', 'ssh', '--',
                'sudo', '/usr/bin/python3', '-c', VM_READER, json.dumps(identity)])
            # The reader source is already retained in this artifact. Avoid
            # duplicating it in every observation's command array.
            capture['command'][-2] = '<VM_READER from capture_process_identity.py>'
            receipt['capture'] = capture
            if capture['returncode']:
                raise RuntimeError('VM process mapping failed')
            receipt['mapping'] = json.loads(capture.pop('stdout'))
            receipt['outcome'] = 'captured'
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            receipt.update(outcome='capture_error', error=repr(error))
        receipt['finished_utc'] = utc()
        output.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(outcome=receipt['outcome'], output=str(args.output))))
    return 0 if receipt['outcome'] == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
