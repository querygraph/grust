"""One fresh, admitted Morrobay cell; retain failures and own only its container."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Literal

HOST = Path('/Users/alexy/src/sail-extensions-gates/pecan-typed-tests-20261001')
ROOT = '/targets/pecan-typed-tests-20261001'
OLD = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
MATRIX = OLD/'harness/run_matrix.py'
MATRIX_SHA = '21d12c888caabb59acece11a2ee27837974c1f34b08cc499600e305d6341e1a0'
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
PYTHON = '/targets/graph-nuts-ffcfbd569/venv/bin/python'
BINARY = '/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release'
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
HEADS = {'baseline': 'cab6bacc0ad0d1fc8b3070e9e4267e99751909fe',
         'candidate': '6ae2e43a903c2cee02da170465c922c72b76198e'}
BOOT = '''import json,os,runpy,sys
paths=json.loads(sys.argv.pop(1))
sys.path[:0]=paths
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
 PYTHONDONTWRITEBYTECODE='1',SPARK_CONNECT_MODE_ENABLED='1',GIT_OPTIONAL_LOCKS='0',
 SAIL_BENCHMARK_RUST_LOG='warn',SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS='900',
 SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS='86400')
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
PROBE = '''import hashlib,json,shutil,sys
from pathlib import Path
root=Path(sys.argv[1]);manifest=json.loads((root/'support/support-manifest.json').read_text())
for n,h in manifest['files_sha256'].items():
 p=root/'support'/n
 assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==h,n
assert hashlib.sha256((root/'support/support-manifest.json').read_bytes()).hexdigest()==sys.argv[2]
assert not (root/'cells'/sys.argv[3]).exists()
memory=Path('/proc/meminfo').read_text()
available=int(next(x.split()[1] for x in memory.splitlines() if x.startswith('MemAvailable:')))*1024
free=shutil.disk_usage('/targets').free
assert free>=12*2**30 and available>=34*2**30
print(json.dumps({'free_bytes':free,'available_bytes':available,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
'''
COLLECT = '''from pathlib import Path
import sys,tarfile
root=Path(sys.argv[1])
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for p in sorted(root.iterdir()):
  if p.is_file() and not p.is_symlink():t.add(p,arcname=p.name,recursive=False)
'''


@dataclass(frozen=True, slots=True)
class Options:
    run_id: str
    revision: Literal['baseline', 'candidate']
    mode: Literal['local', 'process-cluster']
    kind: Literal['smoke', 'wcc']
    support_sha256: str


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path: Path, value: dict[str, Any]) -> None:
    with path.open('x') as stream:
        json.dump({'recorded_utc': datetime.now(timezone.utc).isoformat(), **value}, stream, indent=2)
        stream.write('\n')


def host_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, command in [('vm_stat', ['/usr/bin/vm_stat']),
                          ('swap', ['/usr/sbin/sysctl', 'vm.swapusage']), ('uptime', ['/usr/bin/uptime'])]:
        p = subprocess.run(command, capture_output=True, text=True, timeout=15)
        result[name] = {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    return result


def idle() -> None:
    assert not subprocess.check_output(DOCKER+['ps', '-q'], text=True, timeout=20).strip(), 'another container is running'


def observe(command: list[str], output: Path, label: str,
            stdout: BinaryIO | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    except subprocess.TimeoutExpired as error:
        cleanup: dict[str, Any] = {'error': repr(error), 'command': command}
        try:
            name = command[command.index('--name')+1]
            inspected = subprocess.run(DOCKER+['inspect', name], capture_output=True, text=True, timeout=20)
            cleanup['inspect'] = {'returncode': inspected.returncode, 'stdout': inspected.stdout, 'stderr': inspected.stderr}
            if inspected.returncode == 0:
                item = json.loads(inspected.stdout)[0]
                assert item['Image'] == IMAGE and item['Config']['Entrypoint'] == [PYTHON]
                assert item['Config']['Cmd'] == command[command.index(IMAGE)+1:]
                assert len(item['Mounts']) == 1 and item['Mounts'][0]['Name'] == 'sail-extension-targets'
                assert item['Mounts'][0]['RW'] is False
                if item['State']['Running']:
                    stopped = subprocess.run(DOCKER+['stop', '--time', '10', item['Id']],
                                             capture_output=True, text=True, timeout=30)
                    cleanup['stop'] = {'returncode': stopped.returncode, 'stdout': stopped.stdout, 'stderr': stopped.stderr}
        except BaseException as failed:
            cleanup['cleanup_error'] = repr(failed)
        save(output/(label+'-timeout.json'), cleanup)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--revision', required=True, choices=list(HEADS))
    parser.add_argument('--mode', required=True, choices=['local', 'process-cluster'])
    parser.add_argument('--kind', required=True, choices=['smoke', 'wcc'])
    parser.add_argument('--support-sha256', required=True)
    args = Options(**vars(parser.parse_args()))
    assert re.fullmatch(r'typed-[a-z0-9-]+', args.run_id)
    assert re.fullmatch(r'[0-9a-f]{64}', args.support_sha256)
    assert sys.version_info[:2] == (3, 12)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    assert sha(MATRIX) == MATRIX_SHA
    support_file = OLD/'sem-wcc-support-pins.json'
    assert sha(support_file) == '23ee8504d18cd8db931421f81854e0e01d05dcb6bb5a5c031e1684089f3d69ad'
    original_support = json.loads(support_file.read_text())
    for name, expected in original_support.items():
        assert (OLD/name).resolve().is_relative_to(OLD) and sha(OLD/name) == expected
    sys.path.insert(0, str(OLD/'harness'))
    spec = importlib.util.spec_from_file_location('pinned_run_matrix', MATRIX)
    assert spec is not None and spec.loader is not None
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)
    output = HOST/args.run_id
    output.mkdir(exist_ok=False)
    lock = HOST/'cell.lock'
    lock.mkdir(exist_ok=False)
    save(lock/'owner.json', {'pid': os.getpid(), 'run_id': args.run_id, 'script_sha256': sha(Path(__file__))})
    final: dict[str, Any] = {'outcome': 'error', 'run_id': args.run_id, 'helper_sha256': sha(Path(__file__))}
    closed = False
    try:
        idle()
        manifest = json.loads((HOST/'support-manifest.json').read_text())
        assert sha(HOST/'support-manifest.json') == args.support_sha256
        for name, expected in manifest['files_sha256'].items():
            assert sha(HOST/name) == expected
        save(output/'host-before.json', host_snapshot())
        observer = DOCKER+['run', '--rm', '--name', args.run_id+'-probe', '--read-only', '--network', 'none',
            '--cpus', '1', '--memory', '256m', '--memory-swap', '256m', '--pids-limit', '32',
            '--mount', 'type=volume,source=sail-extension-targets,target=/targets,readonly', '--entrypoint', PYTHON, IMAGE]
        p = observe(observer+['-I', '-B', '-c', PROBE, ROOT, args.support_sha256, args.run_id], output, 'admission')
        save(output/'admission.json', {'returncode': p.returncode, 'stdout': p.stdout.decode(), 'stderr': p.stderr.decode()})
        p.check_returncode()
        config = dict(run_id=args.run_id, docker_context='colima-sail-gate', image=IMAGE,
            target_volume='sail-extension-targets', container_python=PYTHON,
            container_repo=ROOT+'/'+args.revision, container_sail_binary=BINARY,
            harness_source_sha=HEADS[args.revision], environment={},
            limits=dict(cpus=16, cpuset_cpus='0-15', memory_gib=32, outer_timeout_seconds=2700))
        paths = [ROOT+'/'+args.revision+'/examples/extensions/graph-algorithms/src',
                 ROOT+'/candidate/examples/extensions/benchmarks', ROOT+'/deps', ROOT+'/support']
        command = ['-I', '-B', '-c', BOOT, json.dumps(paths), ROOT+'/support/'+('smoke.py' if args.kind == 'smoke' else 'cell.py'),
                   '--repo', config['container_repo'], '--controller-sha', HEADS[args.revision],
                   '--harness-repo', ROOT+'/candidate', '--output', ROOT+'/cells/'+args.run_id, '--mode', args.mode]
        if args.kind == 'wcc':
            inputs = '/targets/sail-stream-experiments-20260930/sem-wcc-pilot-inputs/'
            command += ['--vertices', inputs+'cit-Patents-v.parquet', '--edges', inputs+'cit-Patents-e.parquet',
                        '--reference', inputs+'wcc-membership.i64le', '--method', 'randomized_fused', '--timeout', '1200']
        save(output/'configuration.json', {'config': config, 'command': command, 'support_sha256': args.support_sha256})
        image = matrix.preflight(config, output)
        idle()
        record = matrix.run_container(config, 'sail-'+args.run_id, command, output/'container', image,
                                      240 if args.kind == 'smoke' else 2700, {})
        idle()
        closed = True
        archive = output/'diagnostics.tar'
        with archive.open('xb') as stream:
            p = observe(observer+['-I', '-B', '-c', COLLECT, ROOT+'/cells/'+args.run_id], output, 'collection', stream)
        save(output/'collection.json', {'returncode': p.returncode, 'stderr': p.stderr.decode(), 'sha256': sha(archive)})
        p.check_returncode()
        diagnostic = output/'diagnostics'
        diagnostic.mkdir()
        with tarfile.open(archive) as bundle:
            assert all(m.isfile() and Path(m.name).name == m.name for m in bundle.getmembers())
            bundle.extractall(diagnostic, filter='data')
        result = json.loads((diagnostic/'receipt.json').read_text())
        state = record.get('inspect', {}).get('state', {})
        passed = (result['outcome'] == 'passed' and record.get('attach_returncode') == 0
                  and not record['outer_timeout'] and not record['transport_errors']
                  and record['remove']['returncode'] == 0 and state.get('ExitCode') == 0
                  and state.get('OOMKilled') is False and state.get('Running') is False)
        final.update(outcome='passed' if passed else 'not_passed', producer_outcome=result['outcome'],
                     container_state=state, source=HEADS[args.revision], no_absolute_performance_claim=True)
        assert sha(Path(__file__)) == final['helper_sha256'] and sha(MATRIX) == MATRIX_SHA
        for name, expected in original_support.items():
            assert sha(OLD/name) == expected
    except BaseException as error:
        final.update(outcome='error', error=repr(error))
    finally:
        try:
            save(output/'host-after.json', host_snapshot())
        except BaseException as error:
            final.update(outcome='error', final_observation_error=repr(error))
        try:
            if closed:
                idle()
                (lock/'owner.json').unlink()
                lock.rmdir()
        except BaseException as error:
            final.update(outcome='error', final_cleanup_error=repr(error))
        final['lock_retained'] = lock.exists()
        save(output/'result.json', final)
    print(json.dumps(final), flush=True)
    return 0 if final['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
