"""Own one A2 staging, reference, compatibility, or comparison container.

Host receipts use file fsync and atomic replacement, without a claim of host
directory power-loss durability. Failed/uncertain runs retain the shared lock.
Only the root operator launches this helper; its offline controls mock Docker.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, Field

BASE = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run01')
ROOT = '/targets/sem-review-20261001/A2-run01'
LOCK = BASE.parent / 'gate.lock'
MATRIX = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/harness/run_matrix.py')
MATRIX_SHA = '21d12c888caabb59acece11a2ee27837974c1f34b08cc499600e305d6341e1a0'
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
PYTHON = '/targets/graph-nuts-ffcfbd569/venv/bin/python'
HARNESS_REPO = '/targets/pecan-typed-tests-20261001/candidate'
DEPS = '/targets/pecan-typed-tests-20261001/deps'
CONTROLLER = 'f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'
HARNESS = '6ae2e43a903c2cee02da170465c922c72b76198e'
SAIL = '/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release'
SAIL_SHA = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
GF = '/targets/sem-review-20261001/A1-run02/target/release/graphframes'
GF_SHA = 'b2a7fc0f077fafc158aaa8a45ac32e5f2af5b3d96b8050c348421fa79442722f'
NATIVE_SHA = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
Kind = Literal['validation', 'compatibility', 'cell']

# These scripts use only stdlib until BOOT installs the pinned import paths.
# All arguments are argv JSON/text, with no shell interpolation.
COMMON = r'''
import hashlib, importlib.metadata, json, os, pathlib, shutil, subprocess, sys, traceback
from datetime import datetime, timezone
from typing import Any
spec = json.loads(sys.argv[1])
root = pathlib.Path(spec['root'])
os.environ['GIT_OPTIONAL_LOCKS'] = '0'
sys.dont_write_bytecode = True
def require(value: bool, message: str) -> None:
    if not value: raise ValueError(message)
def sha(path: pathlib.Path) -> str:
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def save(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
def source(path: str, commit: str) -> None:
    command = ['git', '-C', path]
    require(subprocess.check_output(command + ['rev-parse', 'HEAD'], text=True, timeout=30).strip() == commit, 'source HEAD ' + path)
    require(not subprocess.check_output(command + ['status', '--porcelain'], text=True, timeout=30).strip(), 'dirty source ' + path)
    require(subprocess.run(command + ['symbolic-ref', '-q', 'HEAD'], stdout=subprocess.DEVNULL, timeout=30).returncode == 1, 'source not detached ' + path)
def scoped(base: pathlib.Path, name: str) -> pathlib.Path:
    relative = pathlib.PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts and bool(relative.parts), 'unsafe manifest path')
    path = base / relative
    require(path.resolve().is_relative_to(base.resolve()) and not path.is_symlink(), 'unsafe manifest file')
    return path
def guard(staged: bool = True) -> dict[str, Any]:
    source(spec['harness_repo'], spec['harness'])
    if staged: source(str(root / 'repo'), spec['controller'])
    binary = {name: sha(pathlib.Path(spec[name])) for name in ('sail', 'graphframes')}
    require(binary == {'sail': spec['sail_sha256'], 'graphframes': spec['graphframes_sha256']}, 'binary identity')
    identities: dict[str, Any] = {'controller': spec['controller'], 'harness': spec['harness'], 'binary': binary}
    if staged:
        support_path = root / 'support/support-manifest.json'
        payload_path = root / 'payload-manifest.json'
        require(sha(support_path) == spec['support_sha256'] and sha(payload_path) == spec['payload_sha256'], 'manifest identity')
        support = json.loads(support_path.read_text())
        payload = json.loads(payload_path.read_text())
        for name, expected in support['files_sha256'].items():
            require('/' not in name and sha(scoped(root / 'support', name)) == expected, 'support identity ' + name)
        for name, expected in payload['files_sha256'].items():
            require(sha(scoped(root, name)) == expected, 'payload identity ' + name)
        require(sha(root / 'delta.bundle') == payload['delta_bundle_sha256'], 'delta bundle identity')
        package = root / 'repo/examples/extensions/graph-algorithms/src/pyspark_pecan'
        identities.update(support=support, payload=payload,
            package_files={str(p.relative_to(package)): sha(p) for p in sorted(package.rglob('*.py'))},
            harness_files={name: sha(pathlib.Path(spec['harness_repo']) / 'examples/extensions/benchmarks' / name) for name in ('runtime.py', 'measurement.py')})
    return identities
def admission() -> dict[str, Any]:
    lines = pathlib.Path('/proc/meminfo').read_text().splitlines()
    memory = int(next(line.split()[1] for line in lines if line.startswith('MemAvailable:'))) * 1024
    free = shutil.disk_usage('/targets').free
    require(memory >= 34 * 2**30 and free >= 24 * 2**30, 'guest memory/disk admission')
    return {'available_memory_bytes': memory, 'volume_free_bytes': free,
            'boot_id': pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
'''

STAGE = COMMON + r'''
import tarfile
require(not root.exists(), 'staging root already exists')
observations = admission()
before = guard(False)
root.mkdir(parents=True)
receipt: dict[str, Any] = {'outcome': 'checking', 'admission': observations, 'identities_before': before}
save(root / 'stage-receipt.json', receipt)
try:
    with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
        for member in archive:
            require(member.isfile() or member.isdir(), 'nonregular payload member')
            path = scoped(root, member.name)
            if member.isdir(): path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                input_stream = archive.extractfile(member)
                require(input_stream is not None, 'missing tar member stream')
                with path.open('xb') as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
                    output_stream.flush(); os.fsync(output_stream.fileno())
    payload = json.loads((root / 'payload-manifest.json').read_text())
    require(sha(root / 'payload-manifest.json') == spec['payload_sha256'], 'payload manifest')
    require(sha(root / 'support/support-manifest.json') == spec['support_sha256'], 'support manifest')
    for name, expected in payload['files_sha256'].items():
        require(sha(scoped(root, name)) == expected, 'payload file ' + name)
    require(sha(root / 'delta.bundle') == payload['delta_bundle_sha256'], 'delta bundle')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(actual == set(payload['files_sha256']) | {'payload-manifest.json', 'stage-receipt.json'}, 'unlisted payload files')
    subprocess.run(['git', 'clone', '--no-hardlinks', spec['harness_repo'], str(root / 'repo')], check=True, timeout=180)
    subprocess.run(['git', '-C', str(root / 'repo'), 'fetch', str(root / 'delta.bundle'), spec['controller']], check=True, timeout=180)
    subprocess.run(['git', '-C', str(root / 'repo'), 'checkout', '--detach', spec['controller']], check=True, timeout=60)
    receipt['identities_after'] = guard()
    require(receipt['identities_after']['binary'] == before['binary'], 'borrowed binaries changed')
    receipt['outcome'] = 'passed'
except BaseException as error:
    receipt.update(outcome='error', error=repr(error), traceback=traceback.format_exc())
finally:
    receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(root / 'stage-receipt.json', receipt)
print(json.dumps(receipt, allow_nan=False))
sys.exit(0 if receipt['outcome'] == 'passed' else 1)
'''

PROBE = COMMON + r'''
require(not pathlib.Path(spec['output']).exists(), 'output already exists')
print(json.dumps({'admission': admission(), 'identities': guard()}, allow_nan=False))
'''

BOOT = COMMON + r'''
import importlib, runpy
paths = [str(root / 'support'), str(root / 'repo/examples/extensions/graph-algorithms/src'),
         spec['harness_repo'] + '/examples/extensions/benchmarks', spec['deps']]
sys.path[:0] = paths
os.environ.update(PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE='1',
    OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
    SPARK_CONNECT_MODE_ENABLED='1', SAIL_BENCHMARK_RUST_LOG='warn',
    SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS='900', SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS='86400')
import measurement
import runtime
import pyspark_pecan.algorithms as algorithms
def loaded_guard() -> dict[str, Any]:
    value = guard()
    modules = ((runtime, pathlib.Path(spec['harness_repo']) / 'examples/extensions/benchmarks/runtime.py'),
               (measurement, pathlib.Path(spec['harness_repo']) / 'examples/extensions/benchmarks/measurement.py'),
               (algorithms, root / 'repo/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py'))
    loaded: dict[str, Any] = {}
    for module, expected in modules:
        actual = pathlib.Path(module.__file__).resolve()
        require(actual == expected.resolve(), 'loaded module origin ' + module.__name__)
        loaded[module.__name__] = {'path': str(actual), 'sha256': sha(actual)}
    native = runtime.native_package_identity()
    require(spec['native_sha256'] in [h for n, h in native['files_sha256'].items() if n.endswith('.so')], 'native package identity')
    versions = {name: importlib.metadata.version(name) for name in ('pyspark', 'pydantic', 'pydantic_core')}
    require(versions == {'pyspark': '4.0.1', 'pydantic': '2.11.10', 'pydantic_core': '2.33.2'}, 'package versions')
    require(sys.version_info[:2] == (3, 12), 'Python version')
    value.update(loaded_modules=loaded, native=native, packages=runtime.package_versions(), versions=versions)
    return value
output = pathlib.Path(spec['output'])
receipt: dict[str, Any] = {'outcome': 'checking', 'started_utc': datetime.now(timezone.utc).isoformat(),
                         'kind': spec['kind'], 'config_sha256': spec.get('config_sha256')}
code = 1
try:
    require(not output.exists(), 'output already exists')
    receipt['identities_before'] = loaded_guard()
    config = pathlib.Path(spec['config_path'])
    if spec['kind'] == 'cell':
        require(config == root / 'configs' / (spec['run_id'] + '.json'), 'cell config scope')
        text = spec['config_text'].encode('utf-8')
        require(hashlib.sha256(text).hexdigest() == spec['config_sha256'], 'cell config bytes')
        config.parent.mkdir(parents=True, exist_ok=True)
        with config.open('xb') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        require(sha(config) == spec['config_sha256'], 'written cell config')
    script = root / 'support' / spec['helper']
    helper_module = importlib.import_module(script.stem)
    require(pathlib.Path(helper_module.__file__).resolve() == script.resolve(), 'loaded helper origin')
    schema_name = {'cell': 'CellConfig', 'validation': 'InputConfig', 'compatibility': 'Config'}[spec['kind']]
    typed_config = getattr(helper_module, schema_name).model_validate_json(config.read_text())
    require(str(typed_config.output) == str(output), 'configured output tuple')
    if spec['kind'] == 'validation':
        require(str(typed_config.inputs) == spec['inputs'] and typed_config.source == 750000, 'reference configuration tuple')
    else:
        require(str(typed_config.repo) == str(root / 'repo') and str(typed_config.harness_repo) == spec['harness_repo']
                and str(typed_config.support) == str(root / 'support')
                and str(typed_config.graphframes_binary) == spec['graphframes'], 'helper source/storage tuple')
        sail_binary = typed_config.sail_binary if spec['kind'] == 'cell' else typed_config.binary
        require(str(sail_binary) == spec['sail'], 'helper runtime tuple')
    sys.argv = [str(script), '--config', str(config)]
    try:
        runpy.run_path(str(script), run_name='__main__')
        code = 0
    except SystemExit as exited:
        code = exited.code if isinstance(exited.code, int) else (0 if exited.code is None else 1)
    receipt['producer_returncode'] = code
except BaseException as error:
    receipt.update(error=repr(error), traceback=traceback.format_exc())
finally:
    try:
        receipt['identities_after'] = loaded_guard()
        require(receipt.get('identities_before') == receipt['identities_after'], 'bootstrap identities changed')
        if code == 0 and not receipt.get('error'): receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(error=repr(error), final_guard_traceback=traceback.format_exc()); code = 1
    output.mkdir(parents=True, exist_ok=True)
    receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save(output / 'bootstrap-receipt.json', receipt)
sys.exit(code)
'''


@dataclass(frozen=True, slots=True)
class Options:
    action: Literal['stage', 'run']
    run_id: str
    kind: Kind | None = None
    cell_config: Path | None = None


class CommandResult(BaseModel):
    returncode: int | None
    stdout: str = ''
    stderr: str = ''


class CellConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    engine: Literal['graphframes', 'pecan']
    algorithm: Literal['wcc-randomized', 'wcc-min-label', 'bfs']
    mode: Literal['local', 'process-cluster']
    repo: Path
    harness_repo: Path
    support: Path
    output: Path
    inputs: Path
    references: Path
    sail_binary: Path
    graphframes_binary: Path
    timeout_seconds: int = Field(default=1500, ge=30, le=2400)
    reference_receipt_sha256: str
    support_sha256: str


class ProceedScope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dataset: Literal['cit-Patents']
    requires_zero_isolates: Literal[True]
    per_cell_full_oracle: Literal[True]
    generic_signed_wcc_qualified: Literal[False]


class HostReceipt(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    run_id: str
    action: str
    kind: str | None
    started_utc: str
    finished_utc: str | None = None
    outcome: str = 'checking'
    certain_container_closure: bool = False
    lock_retained: bool = True
    producer_outcome: str | None = None
    proceed_scope: ProceedScope | None = None
    error: str | None = None
    traceback: str | None = None
    observations: dict[str, Any] = Field(default_factory=dict)
    records: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    durability_scope: str = 'host file fsync and atomic replace; no host directory power-loss durability qualification'


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path: Path, value: BaseModel | dict[str, Any]) -> None:
    data = value.model_dump(mode='json') if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def capture(command: list[str], timeout: int = 30, stdin: BinaryIO | None = None) -> CommandResult:
    try:
        completed = subprocess.run(command, stdin=stdin, capture_output=True, text=True, timeout=timeout, check=False)
        return CommandResult(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return CommandResult(returncode=None, stderr=repr(error))


def idle() -> None:
    result = capture(DOCKER + ['ps', '-q'])
    require(result.returncode == 0 and not result.stdout.strip(), 'Docker gate busy or unobservable: ' + result.stderr)


def absent(name: str) -> CommandResult:
    result = capture(DOCKER + ['inspect', name])
    stderr = result.stderr.casefold()
    require(result.returncode == 1 and ('no such object' in stderr or 'no such container' in stderr),
            'container absence not proven: ' + name + ' ' + result.stderr)
    return result


def snapshot() -> dict[str, Any]:
    observations: dict[str, Any] = {'apo_free_bytes': shutil.disk_usage(BASE).free}
    require(observations['apo_free_bytes'] >= 24 * 2**30, 'Apo free disk admission')
    for name, command in [('vm_stat', ['/usr/bin/vm_stat']), ('swap', ['/usr/sbin/sysctl', 'vm.swapusage']),
                          ('uptime', ['/usr/bin/uptime'])]:
        result = capture(command, 15)
        observations[name] = result.model_dump()
        require(result.returncode == 0, 'host observation failed: ' + name)
    return observations


def host_pins() -> dict[str, Any]:
    require(sha(MATRIX) == MATRIX_SHA, 'frozen matrix identity')
    support = BASE / 'support'
    manifest = json.loads((support / 'support-manifest.json').read_text())
    payload = json.loads((support / 'payload-manifest.json').read_text())
    require(manifest.get('schema_version') == 1 and payload.get('schema_version') == 1, 'manifest schema')
    for name, expected in manifest['files_sha256'].items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) is not None, 'support basename')
        file = support / name
        require(not file.is_symlink() and sha(file) == expected, 'host support file ' + name)
    require(sha(support / 'delta.bundle') == payload['delta_bundle_sha256'], 'host delta bundle')
    for key, expected in [('controller_sha', CONTROLLER), ('harness_sha', HARNESS)]:
        if key in payload:
            require(payload[key] == expected, 'payload source pin ' + key)
    return {'matrix_sha256': MATRIX_SHA, 'wrapper_sha256': sha(Path(__file__)),
            'support_sha256': sha(support / 'support-manifest.json'),
            'payload_sha256': sha(support / 'payload-manifest.json'),
            'payload_tar_sha256': sha(support / 'payload.tar'), 'support': manifest, 'payload': payload}


def specification(pins: dict[str, Any]) -> dict[str, Any]:
    return {'root': ROOT, 'harness_repo': HARNESS_REPO, 'controller': CONTROLLER, 'harness': HARNESS,
            'deps': DEPS, 'sail': SAIL, 'sail_sha256': SAIL_SHA, 'graphframes': GF,
            'graphframes_sha256': GF_SHA, 'native_sha256': NATIVE_SHA,
            'inputs': '/targets/sail-stream-experiments-20260930/sem-wcc-pilot-inputs',
            'support_sha256': pins['support_sha256'], 'payload_sha256': pins['payload_sha256']}


def matrix_module() -> ModuleType:
    require(sha(MATRIX) == MATRIX_SHA, 'matrix import identity')
    spec = importlib.util.spec_from_file_location('pinned_a2_matrix', MATRIX)
    require(spec is not None and spec.loader is not None, 'matrix import unavailable')
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(MATRIX.parent))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrix_config() -> dict[str, Any]:
    return {'docker_context': 'colima-sail-gate', 'image': IMAGE, 'target_volume': 'sail-extension-targets',
            'container_python': PYTHON, 'container_repo': ROOT + '/repo', 'environment': {},
            'limits': {'cpus': 16, 'cpuset_cpus': '0-15', 'memory_gib': 32}}


def check_matrix_record(record: dict[str, Any], name: str, copied: bool, heavy: bool = True) -> None:
    inspection = record.get('inspect') or {}
    state = inspection.get('state') or {}
    created_id = record.get('create', {}).get('stdout', '').strip()
    require(inspection.get('image') == IMAGE and re.fullmatch(r'[a-f0-9]{64}', created_id) is not None
            and inspection.get('id') == created_id, 'container image/identity')
    require(state.get('Running') is False and state.get('ExitCode') == 0 and state.get('OOMKilled') is False,
            'container exit/OOM state')
    require(record.get('create', {}).get('returncode') == 0 and record.get('attach_returncode') == 0,
            'container launch/attach failed')
    require(record.get('remove', {}).get('returncode') == 0 and not record.get('transport_errors'),
            'container removal/transport failure')
    require(not any(record.get(key) for key in ('outer_timeout', 'operator_interrupted', 'kill', 'forced_cleanup_kill')),
            'container timeout/interruption/forced cleanup')
    if heavy:
        limits = inspection.get('limits') or {}
        require(limits.get('NanoCpus') == 16 * 10**9 and limits.get('CpusetCpus') == '0-15'
                and limits.get('Memory') == 32 * 2**30 and limits.get('MemorySwap') == 32 * 2**30
                and limits.get('Init') is True and limits.get('PidMode') in ('', 'private')
                and limits.get('PidsLimit') == 1024, 'observed execution envelope')
    if copied:
        require(record.get('copied', {}).get('artifacts', {}).get('returncode') == 0, 'required artifact copy')
    record['absence_verified'] = absent(name).model_dump()
    idle()


def owned_small(host: Path, name: str, script: str, spec: dict[str, Any],
                payload: Path | None, copy_source: str | None) -> dict[str, Any]:
    command = DOCKER + ['create', '-i', '--name', name, '--read-only', '--network', 'none', '--cpus', '1',
                       '--memory', '512m', '--memory-swap', '512m', '--pids-limit', '32', '--mount',
                       'type=volume,source=sail-extension-targets,target=/targets' + (',readonly' if payload is None else ''),
                       '--entrypoint', PYTHON, IMAGE, '-I', '-B', '-c', script, json.dumps(spec)]
    record: dict[str, Any] = {'command': command, 'certain_closure': False, 'errors': []}
    save(host / 'orchestration.json', record)
    created = capture(command)
    record['create'] = created.model_dump()
    save(host / 'orchestration.json', record)
    require(created.returncode == 0 and re.fullmatch(r'[a-f0-9]{64}', created.stdout.strip()) is not None,
            'small container create failed or uncertain')
    identifier = created.stdout.strip()
    try:
        if payload is None:
            attached = capture(DOCKER + ['start', '--attach', name], 600)
        else:
            with payload.open('rb') as stream:
                attached = capture(DOCKER + ['start', '--attach', '--interactive', name], 600, stream)
        record['attach'] = attached.model_dump()
    except BaseException as error:  # noqa: BLE001 - preserve owned container cleanup on interruption
        record['errors'].append(repr(error))
    finally:
        try:
            inspected = capture(DOCKER + ['inspect', name])
            record['inspect_command'] = inspected.model_dump()
            require(inspected.returncode == 0, 'owned inspection failed')
            item = json.loads(inspected.stdout)[0]
            require(item['Id'] == identifier and item['Image'] == IMAGE
                    and item['Config']['Entrypoint'] == [PYTHON]
                    and item['Config']['Cmd'] == ['-I', '-B', '-c', script, json.dumps(spec)]
                    and any(m.get('Name') == 'sail-extension-targets' and m.get('Destination') == '/targets'
                            and m.get('RW') is (payload is not None) for m in item['Mounts']), 'small container ownership')
            record['ownership_verified'] = True
            if item['State']['Running']:
                killed = capture(DOCKER + ['kill', name])
                record['kill'] = killed.model_dump()
                require(killed.returncode == 0, 'owned cleanup kill failed')
                inspected = capture(DOCKER + ['inspect', name])
                require(inspected.returncode == 0, 'inspection after kill failed')
                item = json.loads(inspected.stdout)[0]
            record['inspect'] = item
            require(item['State']['Running'] is False, 'owned container still running')
            if copy_source:
                copied = capture(DOCKER + ['cp', name + ':' + copy_source, str(host / 'stage-receipt.json')], 180)
                record['copy'] = copied.model_dump()
                if copied.returncode != 0:
                    record['errors'].append('stage receipt collection failed')
            removed = capture(DOCKER + ['rm', name])
            record['remove'] = removed.model_dump()
            require(removed.returncode == 0, 'owned removal failed')
            record['absence_verified'] = absent(name).model_dump()
            record['certain_closure'] = True
        except BaseException as error:  # noqa: BLE001 - retain uncertain owned-container closure
            record['errors'].append(repr(error))
        save(host / 'orchestration.json', record)
    require(record['certain_closure'] and not record['errors'] and not record.get('kill')
            and record.get('attach', {}).get('returncode') == 0
            and record['inspect']['State']['ExitCode'] == 0 and not record['inspect']['State']['OOMKilled'],
            'small container did not pass cleanly')
    idle()
    return record


def config_for(options: Options, spec: dict[str, Any], host: Path) -> dict[str, Any]:
    kind = options.kind
    require(kind is not None, 'run requires kind')
    spec.update(kind=kind, run_id=options.run_id)
    if kind == 'cell':
        require(options.cell_config is not None, 'cell requires host configuration')
        assert options.cell_config is not None
        raw = options.cell_config.read_bytes()
        text = raw.decode('utf-8')
        config = json.loads(text)
        CellConfiguration.model_validate_json(text)
        expected = {'repo': ROOT + '/repo', 'harness_repo': HARNESS_REPO, 'support': ROOT + '/support',
                    'output': ROOT + '/cells/' + options.run_id, 'references': ROOT + '/references',
                    'inputs': '/targets/sail-stream-experiments-20260930/sem-wcc-pilot-inputs',
                    'sail_binary': SAIL, 'graphframes_binary': GF, 'support_sha256': spec['support_sha256']}
        require(all(config.get(key) == value for key, value in expected.items()), 'cell source/storage tuple')
        require(config.get('engine') in ('pecan', 'graphframes')
                and config.get('algorithm') in ('wcc-randomized', 'wcc-min-label', 'bfs')
                and config.get('mode') in ('local', 'process-cluster'), 'cell execution contract')
        require(re.fullmatch(r'[a-f0-9]{64}', config.get('reference_receipt_sha256', '')) is not None,
                'reference receipt pin')
        with (host / 'cell-config.json').open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        spec.update(helper='supervise_cell.py', output=expected['output'],
                    config_path=ROOT + '/configs/' + options.run_id + '.json', config_text=text,
                    config_sha256=hashlib.sha256(raw).hexdigest())
    else:
        require(options.cell_config is None, 'host cell config is only admitted for cells')
        filename, helper, output = (('prepare-config.json', 'prepare_inputs.py', 'references')
                                    if kind == 'validation' else
                                    ('compatibility-config.json', 'run_compatibility.py', 'compatibility'))
        spec.update(helper=helper, output=ROOT + '/' + output, config_path=ROOT + '/' + filename)
    return spec


def collected_inventory(directory: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'collected symbolic link')
        if path.is_file():
            result[str(path.relative_to(directory))] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
        else:
            require(path.is_dir(), 'collected special file')
    require(bool(result), 'empty artifact collection')
    return result


def producer_check(kind: Kind, artifacts: Path, spec: dict[str, Any]) -> dict[str, Any]:
    boot = json.loads((artifacts / 'bootstrap-receipt.json').read_text())
    require(boot.get('outcome') == 'passed' and boot.get('producer_returncode') == 0
            and boot.get('identities_before') == boot.get('identities_after')
            and boot.get('config_sha256') == spec.get('config_sha256'), 'bootstrap receipt did not pass')
    producer: dict[str, Any] = json.loads((artifacts / 'receipt.json').read_text())
    if kind == 'compatibility':
        require(producer.get('outcome') in ('passed', 'passed_with_known_mismatch'), 'compatibility scoped verdict')
        ProceedScope.model_validate(producer.get('proceed_scope'))
        require(producer.get('generic_signed_id_qualification') is False
                and producer.get('before') == producer.get('after') and bool(producer.get('before')),
                'compatibility scope/identities')
        controls = producer.get('controls') or []
        ids = ['wcc-graphframes', 'wcc-pecan-randomized', 'wcc-pecan-min-label',
               'bfs-graphframes', 'bfs-pecan', 'b9-signed-isolate']
        require([control.get('id') for control in controls] == ids
                and all(control.get('outcome') == 'passed' for control in controls[:-1]), 'ordinary controls')
        require(controls[-1].get('outcome') == ('known_mismatch' if producer['outcome'] == 'passed_with_known_mismatch' else 'passed'),
                'signed witness verdict')
        for control in controls:
            require(control.get('returncode') == 0 and control.get('closure_observed') is True
                    and not any(control.get(key) for key in ('remaining_processes', 'remaining_after_cleanup', 'emergency_cleanup', 'error')),
                    'compatibility control closure')
            files = control.get('result_files') or {}
            require(bool(files), 'compatibility physical output missing')
            for name, identity in files.items():
                relative = Path(name)
                require(not relative.is_absolute() and '..' not in relative.parts, 'control file scope')
                path = artifacts / 'controls' / control['id'] / 'result' / relative
                require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'control physical hash')
    else:
        require(producer.get('outcome') == 'passed', 'producer did not pass')
    if kind == 'cell':
        require(producer.get('config') == json.loads(spec['config_text']), 'producer exact cell config')
        require(producer.get('identities_before') == producer.get('identities_after') and bool(producer.get('identities_before')),
                'producer identities changed/missing')
        require(producer['identities_before'].get('reference_phase', {}).get('validation', {}).get('isolated_vertex_count') == 0,
                'cell reference phase requires zero isolates')
        require(producer.get('engine_returncode') == 0 and producer.get('engine_wait_completed') is True
                and producer.get('execution_verified') is True and not producer.get('outer_timeout')
                and not any(producer.get(key) for key in ('remaining_processes', 'remaining_after_cleanup', 'emergency_cleanup',
                                                         'observer_error', 'final_processes', 'finalization_errors', 'interruption_signals')),
                'producer execution/closure observations')
        correctness = producer.get('correctness') or {}
        files = correctness.get('result_files') or {}
        require(bool(files), 'missing physical correctness files')
        for name, identity in files.items():
            relative = Path(name)
            require(not relative.is_absolute() and '..' not in relative.parts, 'physical output file scope')
            path = artifacts / 'result' / relative
            require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'collected physical hash ' + name)
        require(correctness.get('rows') == 3774768 and correctness.get('unique') == 3774768,
                'physical result cardinality')
        require(correctness.get('membership_mismatches', 0) == 0 and correctness.get('distance_mismatches', 0) == 0,
                'physical oracle mismatch')
    elif kind == 'validation':
        require(producer.get('originals_before') == producer.get('originals_after') and bool(producer.get('originals_before'))
                and bool(producer.get('validation')) and bool(producer.get('certificate')) and bool(producer.get('references')),
                'reference phase incomplete')
        require(producer['validation'].get('isolated_vertex_count') == 0, 'cit-Patents scope requires zero isolates')
        for name in ('ids', 'bfs_distances'):
            reference = producer['references'][name]
            path = artifacts / Path(reference['path']).name
            identity = reference['identity']
            require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'collected reference hash')
    return producer


def release_lock(token: str) -> None:
    owner = json.loads((LOCK / 'owner.json').read_text())
    require(owner.get('token') == token and owner.get('pid') == os.getpid(), 'shared lock ownership changed')
    require({p.name for p in LOCK.iterdir()} == {'owner.json'}, 'unexpected shared lock contents')
    (LOCK / 'owner.json').unlink()
    LOCK.rmdir()


def execute(options: Options) -> int:
    host = BASE / options.run_id
    host.mkdir(exist_ok=False)
    receipt = HostReceipt(run_id=options.run_id, action=options.action, kind=options.kind, started_utc=utc())
    save(host / 'result.json', receipt)
    token = uuid.uuid4().hex
    try:
        LOCK.mkdir(exist_ok=False)
        save(LOCK / 'owner.json', {'pid': os.getpid(), 'token': token, 'run_id': options.run_id,
                                 'action': options.action, 'host': str(host), 'started_utc': utc()})
        idle()
        image = capture(DOCKER + ['image', 'inspect', IMAGE, '--format', '{{.Id}}'])
        require(image.returncode == 0 and image.stdout.strip() == IMAGE, 'gate image identity')
        pins = host_pins()
        save(host / 'support-identities.json', pins)
        receipt.observations['before'] = snapshot()
        save(host / 'result.json', receipt)
        spec = specification(pins)
        if options.action == 'stage':
            small = host / 'stage'
            small.mkdir()
            name = 'sem-review-a2-' + options.run_id + '-stage'
            record = owned_small(small, name, STAGE, spec, BASE / 'support/payload.tar', ROOT + '/stage-receipt.json')
            receipt.records['stage'] = record
            producer = json.loads((small / 'stage-receipt.json').read_text())
            require(producer.get('outcome') == 'passed', 'stage producer did not pass')
            receipt.producer_outcome = 'passed'
        else:
            spec = config_for(options, spec, host)
            save(host / 'configuration.json', {'specification': spec, 'config': matrix_config(),
                                             'guest_command': ['-I', '-B', '-c', BOOT, json.dumps(spec)],
                                             'outer_timeout_seconds': 3600})
            small = host / 'admission'
            small.mkdir()
            record = owned_small(small, 'sem-review-a2-' + options.run_id + '-admission', PROBE, spec, None, None)
            receipt.records['admission'] = record
            receipt.observations['guest_admission'] = json.loads(record['attach']['stdout'])
            save(host / 'result.json', receipt)
            matrix = matrix_module()
            name = 'sem-review-a2-' + options.run_id
            record = matrix.run_container(matrix_config(), name, ['-I', '-B', '-c', BOOT, json.dumps(spec)],
                                          host / 'container', IMAGE, 3600, {'artifacts': spec['output']})
            receipt.records['container'] = record
            save(host / 'container-record.json', record)
            check_matrix_record(record, name, True)
            receipt.certain_container_closure = True
            artifacts = host / 'container/artifacts'
            receipt.artifacts = collected_inventory(artifacts)
            save(host / 'collected-manifest.json', receipt.artifacts)
            assert options.kind is not None
            producer = producer_check(options.kind, artifacts, spec)
            receipt.producer_outcome = producer['outcome']
            if producer.get('proceed_scope') is not None:
                receipt.proceed_scope = ProceedScope.model_validate(producer['proceed_scope'])
        receipt.certain_container_closure = True
        idle()
        receipt.observations['after'] = snapshot()
        require(host_pins() == pins, 'host helper/support identities changed')
        receipt.finished_utc = utc()
        receipt.outcome = ('passed_with_known_mismatch' if receipt.producer_outcome == 'passed_with_known_mismatch' else 'passed')
        save(host / 'result.json', receipt)
        release_lock(token)
        receipt.lock_retained = False
        save(host / 'result.json', receipt)
        return 0
    except BaseException as error:  # noqa: BLE001 - retain failures and the shared lock on interruption
        receipt.outcome = 'error'
        receipt.error = repr(error)
        receipt.traceback = traceback.format_exc()
        receipt.finished_utc = utc()
        receipt.lock_retained = LOCK.exists()
        save(host / 'result.json', receipt)
        return 1


def arguments() -> Options:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'run'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--kind', choices=('validation', 'compatibility', 'cell'))
    parser.add_argument('--cell-config', type=Path)
    parsed = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', parsed.run_id) is not None, 'safe unique run ID required')
    require((parsed.action == 'run') == (parsed.kind is not None), 'only run requires kind')
    require((parsed.kind == 'cell') == (parsed.cell_config is not None), 'only cells require --cell-config')
    return Options(parsed.action, parsed.run_id, parsed.kind, parsed.cell_config)


if __name__ == '__main__':
    sys.exit(execute(arguments()))
