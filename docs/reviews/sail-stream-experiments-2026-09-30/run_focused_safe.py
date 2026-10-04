"""One diagnostic Sail cell; run on Morrobay, retain bulky output in the VM.

Uses the pinned benchmark's command construction, preflight and container
supervision. Copies only top-level diagnostic files, never datasets/staging.
Host process inventory records executable names without command arguments.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    os.environ['PATH'] = '/usr/local/bin:/opt/homebrew/bin:' + os.environ.get('PATH', '')
    parser = argparse.ArgumentParser()
    parser.add_argument('configuration', type=Path)
    parser.add_argument('--bootstrap', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.configuration.read_text())
    root = args.configuration.parent
    docker = ['/usr/local/bin/docker', '--context', config['docker_context']]
    if args.bootstrap:
        code = '''
import json,os,subprocess,sys,shutil
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
source=Path(c['container_repo'])
base='/targets/graph-nuts-ffcfbd569/source'
if not source.exists():
 subprocess.run(['git','clone','--shared','--no-checkout',base,str(source)],check=True)
 subprocess.run(['git','-C',str(source),'fetch','/work/harness.bundle','refs/heads/work/stream-diagnostic-harness'],check=True)
 subprocess.run(['git','-C',str(source),'checkout','--detach',c['harness_source_sha']],check=True)
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==c['harness_source_sha']
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
datasets=Path(c['container_root'])/'datasets'
datasets.mkdir(parents=True,exist_ok=True)
for name in c['datasets']:
 target=datasets/name
 original=Path('/targets/gn-capacity-b87fb27a-hub/datasets')/name
 assert (original/'manifest.json').exists()
 if not target.exists(): target.symlink_to(original,target_is_directory=True)
 assert target.is_symlink() and target.resolve()==original.resolve()
print(json.dumps({'source':str(source),'sha':c['harness_source_sha'],'free_bytes':shutil.disk_usage('/targets').free}))
'''
        command = docker + ['run', '--rm', '--mount',
            'type=volume,source=sail-extension-targets,target=/targets',
            '--mount', f'type=bind,source={root},target=/work,readonly',
            '--workdir', '/targets',
            '--entrypoint', config['container_python'], config['image'],
            '-I', '-c', code, '/work/' + args.configuration.name]
        bootstrap_receipt = root / ('bootstrap-' + args.configuration.stem + '.json')
        if bootstrap_receipt.exists():
            raise FileExistsError(bootstrap_receipt)
        result = subprocess.run(command, text=True, capture_output=True)
        save(bootstrap_receipt, dict(utc=utc(), command=command,
             returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        print(result.stdout, result.stderr, flush=True)
        return result.returncode

    sys.path.insert(0, str(root / 'harness'))
    import run_matrix as matrix
    cells = matrix.plan_cells(config)
    assert len(cells) == 1, 'focused runner requires exactly one cell'
    cell = cells[0]
    output = Path(config['host_output'])
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'configuration.json', config)
    save(output / 'plan.json', dict(cells=cells, command=matrix.cell_command(config, cell)))
    snapshots = {}
    for key, command in [('swap', ['sysctl','vm.swapusage']),
                         ('vm_stat', ['vm_stat']),
                         ('processes', ['ps','-axo','pid,etime,comm']),
                         ('disk', ['df','-h',str(root)])]:
        result = subprocess.run(command, text=True, capture_output=True)
        snapshots[key] = dict(command=command, returncode=result.returncode,
                              stdout=result.stdout, stderr=result.stderr)
    save(output / 'host-before.json', dict(utc=utc(), snapshots=snapshots))
    image = matrix.preflight(config, output)
    name = 'sail-' + config['run_id'] + '-1'
    record = matrix.run_container(config, name, matrix.cell_command(config, cell),
        output / 'cell', image, config['limits']['outer_timeout_seconds'], {})
    # The named volume retains full result and staging trees after container removal.
    cell_path = str(Path(config['container_root']) / 'cells' / cell['cell_id'])
    archive = output / 'diagnostics.tar'
    code = '''
from pathlib import Path
import sys,tarfile
p=Path(sys.argv[1])
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for f in sorted(p.iterdir()):
  if f.is_file() and not f.is_symlink(): t.add(f,arcname=f.name,recursive=False)
'''
    command = docker + ['run', '--rm', '--mount',
        'type=volume,source=sail-extension-targets,target=/targets,readonly',
        '--entrypoint', config['container_python'], image, '-I', '-c', code, cell_path]
    with archive.open('wb') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, timeout=180)
    collection = dict(utc=utc(), command=command, returncode=result.returncode,
                      stderr=result.stderr.decode(), bytes=archive.stat().st_size,
                      sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                      full_artifact_path=cell_path,
                      retention='all full artifacts remain in sail-extension-targets volume')
    save(output / 'collection.json', collection)
    result.check_returncode()
    diagnostics = output / 'diagnostics'
    diagnostics.mkdir()
    with tarfile.open(archive) as bundle:
        # Only flat regular files were selected; check again before extraction.
        for item in bundle.getmembers():
            assert item.isfile() and Path(item.name).name == item.name
        bundle.extractall(diagnostics)
    receipt = json.loads((diagnostics / 'receipt.json').read_text())
    outcome = matrix.classify(record, receipt, config['harness_source_sha'])
    save(output / 'result.json', dict(utc=utc(), outcome=outcome, cell=cell,
        receipt_outcome=receipt.get('outcome'), original_runtime=config['runtime_source_sha'],
        harness=config['harness_source_sha'], error=receipt.get('error'),
        experiment='diagnosis on shared host, not a performance measurement'))
    print(json.dumps(dict(outcome=outcome, receipt_outcome=receipt.get('outcome'),
                          output=str(output))), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
