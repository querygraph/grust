"""Read-only identity and available-disk check before one Morrobay cell.

This supplements the pinned harness. Disk headroom is an admission observation,
not a guarantee that an entire graph run will fit. It acquires no host lock.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


READER = r'''
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
c=json.loads(sys.argv[1])
def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
binary=Path(c['container_sail_binary'])
before=binary.stat()
binary_sha=sha(binary)
after=binary.stat()
assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
source=c['container_repo']
head=subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()
status=subprocess.check_output(['git','-C',source,'status','--porcelain'],text=True).strip()
datasets={}
for name in c['datasets']:
    path=Path(c['container_root'])/'datasets'/name/'manifest.json'
    manifest=json.loads(path.read_text())
    datasets[name]={'path':str(path.resolve()),'sha256':sha(path),
                    'counts':manifest.get('counts'),'canonical':manifest.get('canonical'),
                    'files':len(manifest.get('files',{}))}
native=Path('/targets/graph-nuts-ffcfbd569/venv/lib/python3.12/site-packages/sail_nutmeg/_native.cpython-312-x86_64-linux-gnu.so')
print(json.dumps({'binary_sha256':binary_sha,'binary_bytes':after.st_size,
                 'harness_head':head,'harness_status':status,
                 'native_sha256':sha(native),'datasets':datasets,
                 'free_bytes':shutil.disk_usage('/targets').free,
                 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 'uptime':Path('/proc/uptime').read_text().strip(),
                 'cpu_stat':Path('/proc/stat').read_text().splitlines()[0],
                 'memory_info':Path('/proc/meminfo').read_text(),
                 'kernel_release':os.uname().release}))
'''


def utc():
    return datetime.now(timezone.utc).isoformat()


def capture(command):
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    return dict(command=command, returncode=result.returncode,
                stdout=result.stdout, stderr=result.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configuration', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expected-config-sha256', required=True)
    parser.add_argument('--expected-binary-sha256', required=True)
    parser.add_argument('--minimum-free-bytes', type=int, required=True)
    args = parser.parse_args()
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + os.environ.get('PATH', '')
    with args.output.open('x') as stream:
        receipt = dict(started_utc=utc(), outcome='error',
                       scope='point-in-time identity and disk admission; no host lock or full-run capacity guarantee')
        try:
            data = args.configuration.read_bytes()
            receipt['config_sha256'] = hashlib.sha256(data).hexdigest()
            assert receipt['config_sha256'] == args.expected_config_sha256
            config = json.loads(data)
            docker = ['/usr/local/bin/docker', '--context', config['docker_context']]
            inventory = docker + ['ps', '--format', '{{.ID}} {{.Names}} {{.Image}}']
            receipt['running_before'] = capture(inventory)
            assert receipt['running_before']['returncode'] == 0
            assert not receipt['running_before']['stdout'].strip(), 'running container exists'
            command = docker + ['run', '--rm', '--read-only', '--network', 'none',
                '--memory', '256m', '--memory-swap', '256m', '--cpus', '1', '--pids-limit', '32',
                '--mount', 'type=volume,source=' + config['target_volume'] + ',target=/targets,readonly',
                '--entrypoint', config['container_python'], config['image'],
                '-I', '-B', '-c', READER, json.dumps(config)]
            receipt['observation'] = capture(command)
            assert receipt['observation']['returncode'] == 0
            observed = json.loads(receipt['observation']['stdout'])
            receipt['observed'] = observed
            assert observed['binary_sha256'] == args.expected_binary_sha256
            assert observed['harness_head'] == config['harness_source_sha']
            assert not observed['harness_status']
            assert observed['native_sha256'] == 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
            receipt['minimum_free_bytes'] = args.minimum_free_bytes
            assert args.minimum_free_bytes > 0 and observed['free_bytes'] >= args.minimum_free_bytes
            receipt['running_after'] = capture(inventory)
            assert receipt['running_after']['returncode'] == 0
            assert not receipt['running_after']['stdout'].strip(), 'container started during observation'
            receipt['outcome'] = 'passed'
        except BaseException as error:
            receipt['error'] = repr(error)
            raise
        finally:
            receipt['finished_utc'] = utc()
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'outcome': receipt['outcome'], 'output': str(args.output),
                      'free_bytes': receipt['observed']['free_bytes']}))


if __name__ == '__main__':
    main()
