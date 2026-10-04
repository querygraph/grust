"""Morrobay host wrapper for one pilot; existing harness owns container timeout/cleanup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
TARGETS = '/targets/sail-stream-experiments-20260930'
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
PYTHON = '/targets/graph-nuts-ffcfbd569/venv/bin/python'
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']


def save(path, value):
    with path.open('x') as stream:
        json.dump(dict(recorded_utc=datetime.now(timezone.utc).isoformat(), **value), stream, indent=2)
        stream.write('\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def observe(command, output, label, timeout, stdout=None):
    try:
        return subprocess.run(command, capture_output=stdout is None, stdout=stdout,
            stderr=None if stdout is None else subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        record = dict(command=command, timeout_seconds=timeout,
            stdout=(error.stdout or b'').decode(errors='replace'),
            stderr=(error.stderr or b'').decode(errors='replace'))
        save(output / (label + '-timeout.json'), record)
        name = command[command.index('--name') + 1]
        check = subprocess.run(DOCKER + ['inspect', name], capture_output=True, text=True, timeout=15)
        cleanup = dict(inspect_returncode=check.returncode, inspect_stdout=check.stdout, inspect_stderr=check.stderr)
        if check.returncode == 0:
            item = json.loads(check.stdout)[0]
            assert item['Image'] == IMAGE and item['Config']['Entrypoint'] == [PYTHON]
            assert item['Config']['Cmd'] == command[command.index(IMAGE) + 1:]
            assert len(item['Mounts']) == 1 and item['Mounts'][0]['Name'] == 'sail-extension-targets' and not item['Mounts'][0]['RW']
            if item['State']['Running']:
                stopped = subprocess.run(DOCKER + ['stop', '--time', '10', item['Id']], capture_output=True, text=True, timeout=25)
                cleanup['stop'] = dict(returncode=stopped.returncode, stdout=stopped.stdout, stderr=stopped.stderr)
        save(output / (label + '-timeout-cleanup.json'), cleanup)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['local', 'process-cluster'], required=True)
    p.add_argument('--method', choices=['randomized', 'randomized_fused'], required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--pilot-sha256', required=True)
    args = p.parse_args()
    assert re.fullmatch('sem-wcc-[a-z0-9-]+', args.run_id)
    os.environ['PATH'] = '/usr/local/bin:/opt/homebrew/bin:' + os.environ.get('PATH', '')
    support_file = ROOT / 'sem-wcc-support-pins.json'
    assert digest(support_file) == '23ee8504d18cd8db931421f81854e0e01d05dcb6bb5a5c031e1684089f3d69ad'
    support = json.loads(support_file.read_text())
    assert support['harness/run_matrix.py'] == '21d12c888caabb59acece11a2ee27837974c1f34b08cc499600e305d6341e1a0'
    for name, sha in support.items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT) and digest(path) == sha
    assert not subprocess.check_output(DOCKER + ['ps', '-q'], text=True).strip(), 'another container is running'
    output = ROOT / args.run_id
    output.mkdir()
    cell = TARGETS + '/' + args.run_id
    script = TARGETS + '/sem-wcc-pilot-support/pilot.py'
    inputs = TARGETS + '/sem-wcc-pilot-inputs'
    config = dict(run_id=args.run_id, docker_context='colima-sail-gate', image=IMAGE,
        target_volume='sail-extension-targets', container_python=PYTHON,
        container_repo=TARGETS + '/source-3a9028057',
        container_sail_binary='/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release',
        harness_source_sha='3a9028057c6c6c5034492845926fc4bc18f9626f',
        limits=dict(cpus=16, cpuset_cpus='0-15', memory_gib=32, outer_timeout_seconds=2700),
        environment={})
    command = ['-I', '-B', script, '--repo', config['container_repo'], '--vertices', inputs + '/cit-Patents-v.parquet',
        '--edges', inputs + '/cit-Patents-e.parquet', '--reference', inputs + '/wcc-membership.i64le',
        '--output', cell, '--mode', args.mode, '--method', args.method, '--timeout', '1200']
    save(output / 'configuration.json', dict(config=config, command=command, pilot_sha256=args.pilot_sha256,
        host_wrapper_sha256=digest(Path(__file__))))
    snapshots = {}
    for key, cmd in [('swap_load', ['/usr/sbin/sysctl', 'vm.swapusage', 'vm.loadavg']),
                     ('vm_stat', ['/usr/bin/vm_stat'])]:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
        assert proc.returncode == 0, proc.stderr
        snapshots[key] = dict(command=cmd, stdout=proc.stdout, stderr=proc.stderr)
    save(output / 'host-before.json', snapshots)
    probe = '''
import hashlib,json,shutil,sys
from pathlib import Path
script,cell=map(Path,sys.argv[1:3])
with script.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
assert actual==sys.argv[3] and not cell.exists()
free=shutil.disk_usage('/targets').free
assert free>=12*2**30
memory=Path('/proc/meminfo').read_text()
available=int(next(s.split()[1] for s in memory.splitlines() if s.startswith('MemAvailable:')))*1024
assert available>=34*2**30
print(json.dumps({'pilot_sha256':actual,'free_bytes':free,'available_bytes':available,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''
    observer = DOCKER + ['run', '--rm', '--name', 'sail-' + args.run_id + '-admission', '--read-only',
        '--network', 'none', '--memory', '256m', '--memory-swap', '256m', '--cpus', '1', '--pids-limit', '32',
        '--mount', 'type=volume,source=sail-extension-targets,target=/targets,readonly', '--entrypoint', PYTHON, IMAGE]
    proc = observe(observer + ['-I', '-B', '-c', probe, script, cell, args.pilot_sha256], output, 'admission', 60)
    save(output / 'admission.json', dict(returncode=proc.returncode, stdout=proc.stdout.decode(), stderr=proc.stderr.decode()))
    proc.check_returncode()
    sys.path.insert(0, str(ROOT / 'harness'))
    import run_matrix as matrix
    image = matrix.preflight(config, output)
    record = matrix.run_container(config, 'sail-' + args.run_id, command, output / 'cell', image, 2700, {})
    collect = '''
from pathlib import Path
import sys,tarfile
p=Path(sys.argv[1])
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for f in sorted(p.iterdir()):
  if f.is_file() and not f.is_symlink(): t.add(f,arcname=f.name,recursive=False)
'''
    archive = output / 'diagnostics.tar'
    with archive.open('xb') as stream:
        proc = observe(observer + ['-I', '-B', '-c', collect, cell], output, 'collection', 180, stdout=stream)
    save(output / 'collection.json', dict(returncode=proc.returncode, stderr=proc.stderr.decode(),
        bytes=archive.stat().st_size, sha256=digest(archive), full_output=cell))
    proc.check_returncode()
    diagnostics = output / 'diagnostics'
    diagnostics.mkdir()
    with tarfile.open(archive) as bundle:
        assert all(m.isfile() and Path(m.name).name == m.name for m in bundle.getmembers())
        bundle.extractall(diagnostics, filter='data')
    receipt = json.loads((diagnostics / 'receipt.json').read_text())
    state = record.get('inspect', {}).get('state', {})
    passed = (receipt['outcome'] == 'passed' and record.get('attach_returncode') == 0 and
        not record['outer_timeout'] and not record['transport_errors'] and record['remove']['returncode'] == 0 and
        state.get('ExitCode') == 0 and state.get('OOMKilled') is False and state.get('Running') is False)
    save(output / 'result.json', dict(outcome='passed' if passed else 'not_passed',
        producer_outcome=receipt['outcome'], container_state=state, no_performance_claim=True))
    print(json.dumps(dict(outcome='passed' if passed else 'not_passed', output=str(output))), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
