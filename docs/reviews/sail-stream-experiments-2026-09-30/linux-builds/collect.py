"""Copy completed Docker build receipts/logs to Mac host and Grust evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('container')
parser.add_argument('run')
parser.add_argument('label')
parser.add_argument('launch_stem')
args = parser.parse_args()
local = Path(__file__).resolve().parent / args.label / 'final'
if local.exists():
    raise RuntimeError('final collection destination already exists')
remote = r'''
from datetime import datetime, timezone
import hashlib, io, json, pathlib, re, shutil, subprocess, tarfile
args = ARGS
root = pathlib.Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
inspection = json.loads(subprocess.check_output(docker + ['inspect', args['container']]))[0]
if inspection['State']['Running']:
    raise RuntimeError('cannot collect final logs while build is active')
data = subprocess.check_output(docker + ['cp', args['container'] + ':' + args['run'] + '/rebuild-receipt.json', '-'])
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    receipt = json.loads(archive.extractfile(archive.getmembers()[0]).read())
if receipt['outcome'] == 'running':
    raise RuntimeError('container ended without a final receipt; retain and inspect separately')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = root / (args['label'] + '-build-evidence-' + stamp)
out.mkdir()
files = ['rebuild-receipt.json']
for step in receipt['steps']:
    name = step['name']
    if not re.fullmatch('[a-z0-9-]+', name):
        raise RuntimeError('unexpected log basename')
    files.append(name + '.log')
for name in files:
    subprocess.run(docker + ['cp', args['container'] + ':' + args['run'] + '/' + name, str(out / name)], check=True)
for suffix in ('.json', '.log'):
    path = root / (args['launch_stem'] + suffix)
    if path.is_file():
        shutil.copy2(path, out / path.name)
(out / 'container.json').write_text(json.dumps({key: inspection[key] for key in ('Id', 'Image', 'State')}, indent=2) + '\n')
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
record = dict(collected_utc=datetime.now(timezone.utc).isoformat(), container=args['container'], run=args['run'],
              source_sha=receipt['source_sha'], outcome=receipt['outcome'], directory=str(out), sha256=hashes)
(out / 'collection.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
'''.replace('ARGS', repr(vars(args)))
result = subprocess.run(['ssh', 'morrobay', 'PATH=/usr/local/bin:/usr/bin:/bin python3 -'],
                        input=remote, text=True, capture_output=True, check=True)
record = json.loads(result.stdout)
local.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(['scp', '-r', 'morrobay:' + record['directory'], str(local)], check=True)
for name, expected in record['sha256'].items():
    assert hashlib.sha256((local / name).read_bytes()).hexdigest() == expected, name
print(json.dumps(dict(local=str(local), remote=record['directory'], files=len(record['sha256']),
                     outcome=record['outcome'], source_sha=record['source_sha'], hashes_verified=True), indent=2))
