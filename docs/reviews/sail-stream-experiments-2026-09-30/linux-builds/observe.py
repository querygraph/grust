"""Read-only Docker build observation; retain each receipt snapshot separately."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('container')
parser.add_argument('run')
parser.add_argument('label')
args = parser.parse_args()
remote = r'''
from datetime import datetime, timezone
import io, json, re, subprocess, tarfile
args = ARGS
docker = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
def command(*items):
    return subprocess.check_output(docker + list(items))
def read_file(path):
    data = command('cp', args['container'] + ':' + path, '-')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return archive.extractfile(archive.getmembers()[0]).read()
record = dict(observed_utc=datetime.now(timezone.utc).isoformat(), container=args['container'], run=args['run'])
inspection = json.loads(command('inspect', args['container']))[0]
record['state'] = inspection['State']
record['image'] = inspection['Image']
record['limits'] = {key: inspection['HostConfig'][key] for key in ('NanoCpus', 'CpusetCpus', 'Memory', 'MemorySwap', 'PidsLimit')}
record['running_containers'] = command('ps', '--format', '{{.Names}}').decode().splitlines()
receipt = json.loads(read_file(args['run'] + '/rebuild-receipt.json'))
record['receipt'] = receipt
record['completed_tests'] = {}
for step in receipt['steps']:
    if step['name'].endswith('-tests') and step.get('returncode') == 0:
        log = read_file(args['run'] + '/' + step['name'] + '.log').decode(errors='replace')
        record['completed_tests'][step['name']] = dict(
            summaries=re.findall(r'^test result:.*$', log, re.M),
            binaries=[value if value.startswith('/') else '/targets/' + value
                      for value in re.findall(r'Running .*?\(([^)]+)\)', log)])
if receipt['steps']:
    last = receipt['steps'][-1]['name']
    record['last_log_tail'] = read_file(args['run'] + '/' + last + '.log').decode(errors='replace').splitlines()[-14:]
if record['state']['Running']:
    record['free_bytes'] = int(command('exec', args['container'], 'df', '-B1', '--output=avail', '/targets').decode().splitlines()[-1])
print(json.dumps(record))
'''.replace('ARGS', repr(vars(args)))
result = subprocess.run(['ssh', 'morrobay', 'PATH=/usr/local/bin:/usr/bin:/bin python3 -'],
                        input=remote, text=True, capture_output=True, check=True)
record = json.loads(result.stdout)
out = Path(__file__).resolve().parent / args.label / 'observations'
out.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
path = out / (stamp + '.json')
path.write_text(json.dumps(record, indent=2) + '\n')
receipt = record['receipt']
print(json.dumps(dict(path=str(path), outcome=receipt['outcome'], state=record['state'],
                     free_bytes=record.get('free_bytes'), last_step=receipt['steps'][-1] if receipt['steps'] else None,
                     completed_test_groups=list(record['completed_tests']), tail=record.get('last_log_tail'),
                     running=record['running_containers']), indent=2))
