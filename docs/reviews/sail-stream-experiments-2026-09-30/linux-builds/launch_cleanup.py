"""Run the authorized completed-build private cache cleanup with durable logs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence', required=True)
args = parser.parse_args()
remote = r'''
from datetime import datetime, timezone
import hashlib, json, pathlib, subprocess
args = ARGS
root = pathlib.Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
evidence = pathlib.Path(args['evidence']).resolve(strict=True)
if not evidence.is_relative_to(root) or evidence.parent != root:
    raise RuntimeError('require collected evidence directory directly in experiment root')
receipt = json.loads((evidence / 'rebuild-receipt.json').read_text())
if receipt['source_sha'] != '2894a962076d3cc404dd72ec736ebeb9239901f6' or receipt['outcome'] != 'passed':
    raise RuntimeError('require exact passing 289 receipt')
docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
if subprocess.check_output(docker + ['ps', '-q']).strip():
    raise RuntimeError('a container is running; cleanup requires an idle VM')
prior = json.loads(subprocess.check_output(docker + ['inspect', 'sail-stream-build289']))[0]
image = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
if prior['State']['Running'] or prior['State']['ExitCode'] != 0 or prior['Image'] != image:
    raise RuntimeError('prior build must have exited successfully in pinned image')
script = root / 'cleanup_completed_native.py'
script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
if script_hash != 'b303c57f8229795ffd1861ee28165a1f449a8b7cda0c2d3b10c76d7ef05676e7':
    raise RuntimeError('cleanup script differs from reviewed copy')
name = 'sail-stream-cleanup289-native'
if subprocess.run(docker + ['inspect', name], capture_output=True).returncode == 0:
    raise RuntimeError('cleanup container exists; preserve earlier attempt')
command = docker + ['run', '--name', name, '--init', '--pid=host', '--cpus', '2',
    '--memory', '2g', '--memory-swap', '2g',
    '--mount', 'type=volume,source=sail-extension-targets,target=/targets',
    '--mount', 'type=bind,source=' + str(root) + ',target=/work,readonly', '--workdir', '/targets',
    '--entrypoint', '/targets/sail-stream-2894a962076d/venv/bin/python', image, '-I', '-B',
    '/work/cleanup_completed_native.py', '--evidence', '/work/' + evidence.name]
launch_path = evidence / 'native-cache-cleanup-launch.json'
log_path = evidence / 'native-cache-cleanup.log'
if launch_path.exists() or log_path.exists():
    raise RuntimeError('cleanup launch evidence exists; preserve it')
launch = dict(started_utc=datetime.now(timezone.utc).isoformat(), command=command,
              script_sha256=script_hash, no_running_containers_before=True,
              scope='remove only passed289 own target-native after test binary hashes; originals retained')
launch_path.write_text(json.dumps(launch, indent=2) + '\n')
with log_path.open('x') as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
launch.update(finished_utc=datetime.now(timezone.utc).isoformat(), returncode=result.returncode)
launch_path.write_text(json.dumps(launch, indent=2) + '\n')
inspection = json.loads(subprocess.check_output(docker + ['inspect', name]))[0]
(evidence / 'native-cache-cleanup-container.json').write_text(json.dumps(
    {key: inspection[key] for key in ('Id', 'Image', 'State')}, indent=2) + '\n')
subprocess.run(docker + ['cp', name + ':/targets/sail-stream-2894a962076d/native-cache-cleanup.json',
                        str(evidence / 'native-cache-cleanup.json')], check=False, capture_output=True)
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
         for p in evidence.glob('native-cache-cleanup*') if p.is_file()}
print(json.dumps(dict(returncode=result.returncode, directory=str(evidence), sha256=files)))
'''.replace('ARGS', repr(vars(args)))
result = subprocess.run(['ssh', 'morrobay', 'PATH=/usr/local/bin:/usr/bin:/bin python3 -'],
                        input=remote, text=True, capture_output=True, check=True)
record = json.loads(result.stdout)
local = Path(__file__).resolve().parent / 'integration289' / 'final'
if not local.is_dir():
    raise RuntimeError('local final build evidence is missing')
for name, expected in record['sha256'].items():
    path = local / name
    if path.exists():
        raise RuntimeError('local cleanup evidence exists; do not overwrite')
    subprocess.run(['scp', 'morrobay:' + record['directory'] + '/' + name, str(path)], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('cleanup evidence copy differs: ' + name)
print(json.dumps(record, indent=2))
raise SystemExit(record['returncode'])
