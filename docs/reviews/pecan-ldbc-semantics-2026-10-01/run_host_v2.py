"""One admitted local LDBC correctness suite; preserve evidence and closure."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOST = Path('/tmp/pecan-ldbc-20261001')
GUEST = '/targets/pecan-ldbc-semantics-20261001-run02'
REPO = '/targets/pecan-typed-tests-20261001/candidate'
SOURCE = '6ae2e43a903c2cee02da170465c922c72b76198e'
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
PYTHON = '/targets/graph-nuts-ffcfbd569/venv/bin/python'
BINARY = '/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release'
MATRIX = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/harness/run_matrix.py')
MATRIX_SHA = '21d12c888caabb59acece11a2ee27837974c1f34b08cc499600e305d6341e1a0'
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']

STAGE = '''import io,json,pathlib,shutil,sys,tarfile
r=pathlib.Path(sys.argv[1])
assert not r.exists(), 'new suite path already exists'
memory=pathlib.Path('/proc/meminfo').read_text()
avail=int(next(x.split()[1] for x in memory.splitlines() if x.startswith('MemAvailable:')))*1024
free=shutil.disk_usage('/targets').free
assert avail>=6*2**30 and free>=2*2**30, 'correctness admission failed'
r.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.issym() and not m.islnk()
  p=pathlib.Path(m.name)
  assert not p.is_absolute() and '..' not in p.parts
  out=r/p;out.parent.mkdir(parents=True,exist_ok=True)
  f=t.extractfile(m);assert f is not None
  with out.open('xb') as w: shutil.copyfileobj(f,w)
print(json.dumps({'available_bytes':avail,'free_bytes':free,'root':str(r)}))
'''
BOOT = '''import json,os,runpy,sys
paths=json.loads(sys.argv.pop(1));sys.path[:0]=paths
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
 PYTHONDONTWRITEBYTECODE='1',SPARK_CONNECT_MODE_ENABLED='1',GIT_OPTIONAL_LOCKS='0',
 SAIL_BENCHMARK_RUST_LOG='warn',SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS='900',
 SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS='86400')
sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict[str, Any]) -> None:
    with path.open('x') as stream:
        json.dump({'recorded_utc': datetime.now(timezone.utc).isoformat(), **value}, stream, indent=2)
        stream.write('\n')


def capture(command: list[str], timeout: int = 30) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return {'command': command, 'returncode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def idle() -> None:
    assert not subprocess.check_output(DOCKER+['ps', '-q'], text=True, timeout=20).strip(), 'context busy'


def main() -> int:
    output = HOST/'host-run02'
    output.mkdir(exist_ok=False)
    lock = HOST/'execution.lock'
    lock.mkdir(exist_ok=False)
    save(lock/'owner.json', {'pid': os.getpid(), 'source': SOURCE, 'guest': GUEST})
    final: dict[str, Any] = {'outcome': 'error', 'source': SOURCE, 'performance_claim': False}
    try:
        idle()
        assert sha(MATRIX) == MATRIX_SHA
        helper = HOST/'run_ldbc_v2.py'
        assert helper.is_file()
        files = [helper, *sorted(p for p in (HOST/'inputs').rglob('*') if p.is_file())]
        manifest = {str(p.relative_to(HOST)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files}
        save(output/'support-manifest.json', {'files': manifest})
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode='w') as bundle:
            for path in files:
                assert not path.is_symlink()
                bundle.add(path, arcname=str(path.relative_to(HOST)), recursive=False)
        stage_command = DOCKER+['run', '--rm', '-i', '--name', 'pecan-ldbc-stage-run02',
            '--read-only', '--network', 'none', '--cpus', '1', '--memory', '256m',
            '--memory-swap', '256m', '--pids-limit', '32', '--mount',
            'type=volume,source=sail-extension-targets,target=/targets', '--entrypoint', PYTHON,
            IMAGE, '-I', '-B', '-c', STAGE, GUEST]
        stage = subprocess.run(stage_command, input=payload.getvalue(), capture_output=True, timeout=30)
        save(output/'stage.json', {'command': stage_command, 'returncode': stage.returncode,
                                 'stdout': stage.stdout.decode(), 'stderr': stage.stderr.decode()})
        stage.check_returncode()
        idle()
        save(output/'host-before.json', {name: capture(cmd) for name, cmd in [
            ('memory', ['/usr/bin/vm_stat']), ('swap', ['/usr/sbin/sysctl', 'vm.swapusage']),
            ('load', ['/usr/bin/uptime'])]})
        sys.path.insert(0, str(MATRIX.parent))
        spec = importlib.util.spec_from_file_location('pinned_run_matrix', MATRIX)
        assert spec is not None and spec.loader is not None
        matrix = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matrix)
        config = dict(run_id='pecan-ldbc-semantics-run02', docker_context='colima-sail-gate',
            image=IMAGE, target_volume='sail-extension-targets', container_python=PYTHON,
            container_repo=REPO, container_sail_binary=BINARY, harness_source_sha=SOURCE,
            environment={}, limits=dict(cpus=2, cpuset_cpus='0-1', memory_gib=4,
                                         outer_timeout_seconds=900))
        paths = [REPO+'/examples/extensions/graph-algorithms/src',
                 REPO+'/examples/extensions/benchmarks', '/targets/pecan-typed-tests-20261001/deps']
        command = ['-I', '-B', '-c', BOOT, json.dumps(paths), GUEST+'/run_ldbc_v2.py',
                   '--repo', REPO, '--inputs', GUEST+'/inputs', '--output', GUEST+'/output']
        save(output/'configuration.json', {'config': config, 'command': command})
        image = matrix.preflight(config, output)
        idle()
        record = matrix.run_container(config, 'sail-pecan-ldbc-semantics-run02', command,
                                      output/'container', image, 900, {'results': GUEST+'/output'})
        save(output/'container-record.json', record)
        idle()
        state = (record.get('inspect') or {}).get('state', {})
        producer_path = output/'container/results/receipt.json'
        producer = json.loads(producer_path.read_text()) if producer_path.is_file() else None
        expected = {f'test-{a}-{d}--{a}' for a in ('bfs', 'pr', 'wcc', 'sssp')
                    for d in ('directed', 'undirected')}
        expected |= {f'example-{d}--{a}' for d in ('directed', 'undirected')
                     for a in ('bfs', 'pr', 'wcc', 'sssp')}
        cells = producer.get('cells', []) if producer else []
        producer_pass = bool(producer and producer.get('outcome') == 'passed'
            and len(cells) == 16 and {c['case'] for c in cells} == expected
            and all(c.get('outcome') == 'passed' for c in cells)
            and not producer.get('cleanup_errors') and not producer.get('not_run'))
        success = (record.get('attach_returncode') == 0 and state.get('ExitCode') == 0
                   and state.get('Running') is False and state.get('OOMKilled') is False
                   and record.get('remove', {}).get('returncode') == 0
                   and not record['outer_timeout'] and not record['transport_errors']
                   and producer_pass)
        final.update(outcome='passed' if success else 'not_passed', container_state=state,
                     attach_returncode=record.get('attach_returncode'), producer_pass=producer_pass,
                     completed_cells=len(cells), certain_container_closure=bool(
                         state.get('Running') is False
                         and record.get('remove', {}).get('returncode') == 0
                         and not record['transport_errors']))
        for path in files:
            assert sha(path) == manifest[str(path.relative_to(HOST))]['sha256'], 'support changed during run'
        assert sha(MATRIX) == MATRIX_SHA
    except BaseException as error:
        final.update(outcome='error', error=repr(error))
    finally:
        try:
            idle()
            (lock/'owner.json').unlink()
            lock.rmdir()
        except BaseException as error:
            final['closure_error'] = repr(error)
        final['lock_retained'] = lock.exists()
        save(output/'result.json', final)
        archive = Path('/Volumes/Apo/graph-tests/results/pecan-ldbc-semantics-20261001-run02')
        try:
            assert Path('/Volumes/Apo').is_mount()
            archive.mkdir(exist_ok=False)
            for path in HOST.iterdir():
                if path.is_dir():
                    shutil.copytree(path, archive/path.name)
                elif path.is_file():
                    shutil.copy2(path, archive/path.name)
        except BaseException as error:
            save(output/'archive-error.json', {'error': repr(error)})
            final['archive_error'] = repr(error)
        final['archive_path'] = str(archive)
        final['archive_outcome'] = 'error' if final.get('archive_error') else 'copied'
        temporary = output/'result-final.json.tmp'
        save(temporary, final)
        temporary.replace(output/'result.json')
        if not final.get('archive_error'):
            shutil.copy2(output/'result.json', archive/'host-run02/result.json')
    print(json.dumps(final), flush=True)
    return 0 if final['outcome'] == 'passed' and not final.get('closure_error') and not final.get('archive_error') else 1


if __name__ == '__main__':
    raise SystemExit(main())
