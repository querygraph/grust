"""Launch the staged host-only build after successful build/cleanup evidence."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence', required=True, help='Collected evidence directory on Morrobay')
args = parser.parse_args()
remote = r'''
from datetime import datetime, timezone
import hashlib, json, pathlib, subprocess
args = ARGS
root = pathlib.Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
evidence = pathlib.Path(args['evidence'])
if not evidence.resolve().is_relative_to(root):
    raise RuntimeError('evidence is outside the experiment directory')
receipt = json.loads((evidence / 'rebuild-receipt.json').read_text())
cleanup = json.loads((evidence / 'native-cache-cleanup.json').read_text())
seed_sha = '2894a962076d3cc404dd72ec736ebeb9239901f6'
sha = '56194b170155301ba91077f0ba3df31fe2c78b6b'
if receipt['source_sha'] != seed_sha or receipt['outcome'] != 'passed' or receipt.get('seed_unchanged') is not True:
    raise RuntimeError('prior native/host build did not pass')
if cleanup['outcome'] != 'passed' or cleanup['cache_absent'] is not True:
    raise RuntimeError('authorized private native cache cleanup did not pass')
docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
if subprocess.check_output(docker + ['ps', '-q']).strip():
    raise RuntimeError('a container is running; no overlapping graph/build workloads allowed')
prior = json.loads(subprocess.check_output(docker + ['inspect', 'sail-stream-build289']))[0]
if prior['State']['Running'] or prior['State']['ExitCode'] != 0:
    raise RuntimeError('prior build container did not exit successfully')
image = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
if prior['Image'] != image:
    raise RuntimeError('prior build image differs from pin')
script = root / 'rebuild_compact_host.py'
script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
if script_hash != '2175661a2dfd6917404c4a88cb429cab282618968012f53ae82b856f1c2dc9ae':
    raise RuntimeError('host-only script differs from reviewed copy')
bundle = root / 'sail-compact-struct-min-56194b170.bundle'
bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
if bundle_hash != '2839e555ccfb50026687bd5c720617592c423df09ef6bc7d4065ef0866a9f8eb':
    raise RuntimeError('bundle differs from exact gated commit')
name = 'sail-stream-build561-host'
if subprocess.run(docker + ['inspect', name], capture_output=True).returncode == 0:
    raise RuntimeError('build container name already exists; preserve its evidence')
command = docker + ['run', '--name', name, '--init', '--cpus', '16', '--cpuset-cpus', '0-15',
    '--memory', '48g', '--memory-swap', '48g', '--pids-limit', '2048',
    '--mount', 'type=volume,source=sail-extension-targets,target=/targets',
    '--mount', 'type=bind,source=' + str(root) + ',target=/work,readonly', '--workdir', '/targets',
    '--entrypoint', '/targets/sail-stream-2894a962076d/venv/bin/python', image, '-I', '-B',
    '/work/rebuild_compact_host.py', '--sha', sha, '--seed-sha', seed_sha,
    '--seed', '/targets/sail-stream-2894a962076d',
    '--bundle', '/work/' + bundle.name, '--bundle-ref', 'refs/heads/work/compact-struct-min',
    '--bundle-sha256', bundle_hash, '--image-id', image, '--jobs', '16']
launch = root / 'compact561-host-launch.json'
log_path = root / 'compact561-host-launch.log'
if launch.exists() or log_path.exists():
    raise RuntimeError('launch record exists; do not overwrite')
with log_path.open('x') as log:
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
record = dict(utc=datetime.now(timezone.utc).isoformat(), pid=process.pid, command=command,
              script_sha256=script_hash, bundle_sha256=bundle_hash, native_source_sha=seed_sha,
              host_source_sha=sha, prior_evidence=str(evidence), no_running_containers_before=True,
              scope='host-only build; unchanged native wheel/venv from passing289; no graph workload')
launch.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
'''.replace('ARGS', repr(vars(args)))
result = subprocess.run(['ssh', 'morrobay', 'PATH=/usr/local/bin:/usr/bin:/bin python3 -'],
                        input=remote, text=True, capture_output=True, check=True)
record = json.loads(result.stdout)
out = Path(__file__).resolve().parent / 'compact561-host'
out.mkdir(exist_ok=True)
(out / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
