"""Preserve a read-only host-cache inspection before an explicitly selected apply.

Both modes require completed, collected builds and no other Docker containers.
The apply path only invokes cleanup_host_caches.py with its preserved inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', required=True, choices=('inspect', 'apply'))
parser.add_argument('--evidence289', required=True)
parser.add_argument('--evidence561', required=True)
parser.add_argument('--inspection')
args = parser.parse_args()
if (args.mode == 'apply') != bool(args.inspection):
    parser.error('apply requires the remote inspection.json path; inspect does not')
args.inspection_sha256 = None
if args.mode == 'apply':
    local_inspection = (Path(__file__).resolve().parent / 'host-cache-cleanup' /
                        Path(args.inspection).parent.name / 'inspection.json')
    if not local_inspection.is_file():
        parser.error('inspection must have been durably collected locally before apply')
    args.inspection_sha256 = hashlib.sha256(local_inspection.read_bytes()).hexdigest()

remote = r'''
from datetime import datetime, timezone
import hashlib, json, pathlib, subprocess
args = ARGS
root = pathlib.Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
image = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
script_hash = 'afce29ac5e36dfa4c71d9f561b09d33d63e268e1234fbdc05d056ee5d4b5b521'
if hashlib.sha256((root / 'cleanup_host_caches.py').read_bytes()).hexdigest() != script_hash:
    raise RuntimeError('cleanup script differs from reviewed copy')
if subprocess.check_output(docker + ['ps', '-q']).strip():
    raise RuntimeError('host-cache inspection/cleanup requires all other containers stopped')
builds = [('sail-stream-build289', '2894a962076d3cc404dd72ec736ebeb9239901f6', 'evidence289'),
          ('sail-stream-build561-host', '56194b170155301ba91077f0ba3df31fe2c78b6b', 'evidence561')]
prior_containers, evidence = {}, {}
for name, sha, key in builds:
    directory = pathlib.Path(args[key]).resolve(strict=True)
    if directory.parent != root:
        raise RuntimeError('build evidence must be directly under experiment root')
    receipt = json.loads((directory / 'rebuild-receipt.json').read_text())
    if (receipt.get('source_sha') != sha or receipt.get('outcome') != 'passed'
            or receipt.get('seed_unchanged') is not True):
        raise RuntimeError('both exact builds and final seed guards must have passed')
    inspection = json.loads(subprocess.check_output(docker + ['inspect', name]))[0]
    if inspection['State']['Running'] or inspection['State']['ExitCode'] != 0 or inspection['Image'] != image:
        raise RuntimeError('both build containers must have exited0 in the pinned image')
    prior_containers[name] = {key: inspection[key] for key in ('Id', 'Image', 'State')}
    evidence[key] = '/work/' + directory.name
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
directory = root / ('host-cache-cleanup-' + args['mode'] + '-' + stamp)
directory.mkdir()
name = 'sail-host-cache-' + args['mode'] + '-' + stamp.lower()
mount = 'type=volume,source=sail-extension-targets,target=/targets'
if args['mode'] == 'inspect':
    mount += ',readonly'
command = docker + ['run', '--name', name, '--init', '--pid=host', '--cpus', '2',
    '--memory', '2g', '--memory-swap', '2g', '--mount', mount,
    '--mount', 'type=bind,source=' + str(root) + ',target=/work,readonly',
    '--workdir', '/targets', '--entrypoint', '/targets/sail-stream-2894a962076d/venv/bin/python',
    image, '-I', '-B', '/work/cleanup_host_caches.py',
    '--evidence289', evidence['evidence289'], '--evidence561', evidence['evidence561']]
inspection_hash = None
if args['mode'] == 'apply':
    inspection_path = pathlib.Path(args['inspection']).resolve(strict=True)
    if inspection_path.parent.parent != root or inspection_path.name != 'inspection.json':
        raise RuntimeError('apply requires a retained inspection under the experiment root')
    inspection_hash = hashlib.sha256(inspection_path.read_bytes()).hexdigest()
    if inspection_hash != args['inspection_sha256']:
        raise RuntimeError('remote inspection differs from the durably collected local copy')
    command += ['--apply', '--inspection', '/work/' + str(inspection_path.relative_to(root)),
                '--inspection-sha256', inspection_hash]
launch = dict(started_utc=datetime.now(timezone.utc).isoformat(), command=command,
              mode=args['mode'], script_sha256=script_hash, inspection_sha256=inspection_hash,
              no_running_containers_before=True, prior_containers=prior_containers,
              scope='only completed task-owned289/561 host caches; original ffcf seeds retained')
(directory / 'launch.json').write_text(json.dumps(launch, indent=2) + '\n')
with (directory / 'command.log').open('x') as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
launch.update(finished_utc=datetime.now(timezone.utc).isoformat(), returncode=result.returncode)
(directory / 'launch.json').write_text(json.dumps(launch, indent=2) + '\n')
current = json.loads(subprocess.check_output(docker + ['inspect', name]))[0]
(directory / 'container.json').write_text(json.dumps(
    {key: current[key] for key in ('Id', 'Image', 'State')}, indent=2) + '\n')
record = None
if args['mode'] == 'inspect' and result.returncode == 0:
    record = json.loads((directory / 'command.log').read_text())
    (directory / 'inspection.json').write_text(json.dumps(record, indent=2) + '\n')
elif args['mode'] == 'apply':
    subprocess.run(docker + ['cp', name + ':/targets/sail-compact-host-56194b170155/host-cache-cleanup.json',
                            str(directory / 'host-cache-cleanup.json')], check=False, capture_output=True)
    if (directory / 'host-cache-cleanup.json').exists():
        record = json.loads((directory / 'host-cache-cleanup.json').read_text())
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
(directory / 'collection.json').write_text(json.dumps(dict(collected_utc=datetime.now(timezone.utc).isoformat(),
    sha256=files, returncode=result.returncode), indent=2) + '\n')
files['collection.json'] = hashlib.sha256((directory / 'collection.json').read_bytes()).hexdigest()
print(json.dumps(dict(returncode=result.returncode, directory=str(directory), sha256=files, record=record)))
'''.replace('ARGS', repr(vars(args)))
result = subprocess.run(['ssh', 'morrobay', 'PATH=/usr/local/bin:/usr/bin:/bin python3 -'],
                        input=remote, text=True, capture_output=True, check=True)
record = json.loads(result.stdout)
local = Path(__file__).resolve().parent / 'host-cache-cleanup' / Path(record['directory']).name
local.mkdir(parents=True, exist_ok=False)
for name, expected in record['sha256'].items():
    path = local / name
    subprocess.run(['scp', 'morrobay:' + record['directory'] + '/' + name, str(path)], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('cleanup evidence copy differs: ' + name)
record['local'] = str(local)
print(json.dumps(record, indent=2))
raise SystemExit(record['returncode'])
