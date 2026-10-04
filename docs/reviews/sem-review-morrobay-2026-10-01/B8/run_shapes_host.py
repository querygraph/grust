"""Own one B8 staging, reference, or paired shape container.

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
from typing import Any, BinaryIO, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

BASE = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01')
ROOT = '/targets/sem-review-20261001/B8-run01'
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
NATIVE_SHA = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
Kind = Literal['reference', 'cell']

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
def quiet() -> None:
    for path in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            if int(path.name) in (1, os.getpid()): continue
            raw = (path / 'stat').read_text()
            require(raw[raw.rfind(')') + 2:].split()[0] in ('Z', 'X'), 'private container contains another live process')
        except FileNotFoundError: continue
def guard(staged: bool = True) -> dict[str, Any]:
    source(spec['harness_repo'], spec['harness'])
    if staged: source(str(root / 'repo'), spec['controller'])
    binary = {'sail': sha(pathlib.Path(spec['sail']))}
    require(binary == {'sail': spec['sail_sha256']}, 'binary identity')
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
    require(memory >= 34 * 2**30 and free >= spec['guest_reserve_bytes'], 'guest memory/disk admission')
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
    require(config == root / 'configs' / (spec['run_id'] + '.json'), 'helper config scope')
    text = spec['config_text'].encode('utf-8')
    require(hashlib.sha256(text).hexdigest() == spec['config_sha256'], 'helper config bytes')
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open('xb') as stream:
        stream.write(text); stream.flush(); os.fsync(stream.fileno())
    require(sha(config) == spec['config_sha256'], 'written helper config')
    script = root / 'support' / spec['helper']
    helper_module = importlib.import_module(script.stem)
    require(pathlib.Path(helper_module.__file__).resolve() == script.resolve(), 'loaded helper origin')
    schema_name = 'CellConfig' if spec['kind'] == 'cell' else 'InputConfig'
    typed_config = getattr(helper_module, schema_name).model_validate_json(config.read_text())
    require(str(typed_config.output) == str(output), 'configured output tuple')
    if spec['kind'] == 'cell':
        require(str(typed_config.repo) == str(root / 'repo') and str(typed_config.harness_repo) == spec['harness_repo']
                and str(typed_config.support) == str(root / 'support') and str(typed_config.binary) == spec['sail'],
                'helper source/storage tuple')
        require(typed_config.minimum_free_bytes == spec['guest_reserve_bytes'], 'declared cell disk reserve')
    require(str(typed_config.vertices) == spec['vertices'] and str(typed_config.edges) == spec['edges'], 'input tuple')
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
    try:
        inventory: dict[str, Any] = {}
        for path in sorted(output.rglob('*')):
            require(not path.is_symlink(), 'archive symlink')
            if path.is_file(): inventory[str(path.relative_to(output))] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
            else: require(path.is_dir(), 'archive special file')
        require(bool(inventory), 'empty guest archive')
        save(output / 'archive-manifest.json', {'schema_version': 1, 'files': inventory})
    except BaseException:
        traceback.print_exc(); code = 1
sys.exit(code)
'''


REMOVE = COMMON + r'''
output = pathlib.Path(spec['output'])
require(output == root / 'cells' / spec['run_id'] and output.resolve() == output
        and root.resolve() == root and not output.is_symlink(), 'owned cell payload scope')
before = guard()
require(sha(output / 'archive-manifest.json') == spec['archive_sha256'], 'archived manifest identity')
manifest = json.loads((output / 'archive-manifest.json').read_text())
actual: dict[str, Any] = {}
for path in sorted(output.rglob('*')):
    require(not path.is_symlink(), 'payload symlink')
    if path.is_file() and path != output / 'archive-manifest.json':
        actual[str(path.relative_to(output))] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    else: require(path.is_dir() or path == output / 'archive-manifest.json', 'payload special file')
require(actual == manifest['files'], 'payload changed after archive')
receipt = json.loads((output / 'receipt.json').read_text())
boot = json.loads((output / 'bootstrap-receipt.json').read_text())
require(receipt['outcome'] == 'passed' and boot['outcome'] == 'passed' and receipt['execution_verified'] is True
        and receipt.get('ownership_admitted') is True and not receipt.get('preexisting_processes'),
        'failed/unverified payload retained')
require(not any(receipt.get(key) for key in ('remaining_processes', 'remaining_after_cleanup', 'emergency_cleanup',
    'final_processes', 'finalization_errors', 'interruption_signals')), 'cell ownership closure incomplete')
quiet()
shutil.rmtree(output)
require(not output.exists() and guard() == before, 'removed scope or borrowed identity changed')
quiet()
print(json.dumps({'outcome': 'passed', 'removed': str(output), 'archive_sha256': spec['archive_sha256']}, allow_nan=False))
'''


@dataclass(frozen=True, slots=True)
class Options:
    action: Literal['stage', 'run']
    run_id: str
    kind: Kind | None = None
    config: Path | None = None
    campaign: Path | None = None


class CommandResult(BaseModel):
    returncode: int | None
    stdout: str = ''
    stderr: str = ''


class CaptureAPI(Protocol):
    def __call__(self, argv: list[str], timeout: int = 60) -> dict[str, Any]: ...


class MatrixAPI(Protocol):
    capture: CaptureAPI

    def run_container(self, config: dict[str, Any], name: str, command: list[str],
                      output: Path, image: str, timeout: int,
                      copy_paths: dict[str, str]) -> dict[str, Any]: ...


class Campaign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    host_root: Path
    guest_root: str
    archive_reserve_bytes: int = Field(default=24 * 2**30, ge=24 * 2**30)
    guest_reserve_bytes: int = Field(default=256 * 2**30, ge=24 * 2**30)
    archive_copy_timeout_seconds: int = Field(default=1800, ge=180, le=7200)
    reference_timeout_seconds: int = Field(default=7200, ge=3600, le=43200)
    cell_timeout_seconds: int = Field(default=3600, ge=3000, le=7200)


class CellConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
    shape: Literal['adjacency', 'representatives', 'min-label-initial-round']
    variant: Literal['union', 'array-explode']
    repo: Path
    harness_repo: Path
    support: Path
    output: Path
    vertices: Path
    edges: Path
    references: Path
    binary: Path
    timeout_seconds: int = Field(default=1500, ge=30, le=2400)
    minimum_free_bytes: int = Field(default=24 * 2**30, ge=24 * 2**30)
    reference_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    support_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


CAMPAIGN = Campaign(host_root=BASE, guest_root=ROOT)


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
    payload_removed: bool = False
    archive_verified: bool = False
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
    require(observations['apo_free_bytes'] >= CAMPAIGN.archive_reserve_bytes, 'Apo free disk admission')
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
            'deps': DEPS, 'sail': SAIL, 'sail_sha256': SAIL_SHA, 'native_sha256': NATIVE_SHA,
            'guest_reserve_bytes': CAMPAIGN.guest_reserve_bytes,
            'support_sha256': pins['support_sha256'], 'payload_sha256': pins['payload_sha256']}


def matrix_module() -> ModuleType:
    require(sha(MATRIX) == MATRIX_SHA, 'matrix import identity')
    spec = importlib.util.spec_from_file_location('pinned_b8_matrix', MATRIX)
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


def matrix_run(module: ModuleType, name: str, command: list[str], output: Path,
               artifacts: str, outer_timeout_seconds: int) -> dict[str, Any]:
    api = cast(MatrixAPI, module)
    original = api.capture
    owned_copy = ['docker', '--context', 'colima-sail-gate', 'cp', name + ':' + artifacts + '/.',
                  str(output / 'artifacts')]
    def archived_capture(argv: list[str], timeout: int = 60) -> dict[str, Any]:
        copying = argv == owned_copy
        effective = max(timeout, CAMPAIGN.archive_copy_timeout_seconds) if copying else timeout
        return original(argv, timeout=effective)
    api.capture = archived_capture
    try:
        return api.run_container(matrix_config(), name, command, output, IMAGE,
                                 outer_timeout_seconds, {'artifacts': artifacts})
    finally:
        api.capture = original


def check_matrix_record(record: dict[str, Any], name: str, copied: bool, heavy: bool = True) -> None:
    inspection = record.get('inspect') or {}
    state = inspection.get('state') or {}
    created_id = record.get('create', {}).get('stdout', '').strip()
    require(inspection.get('image') == IMAGE and re.fullmatch(r'[a-f0-9]{64}', created_id) is not None
            and inspection.get('id') == created_id, 'container image/identity')
    require(state.get('Running') is False and isinstance(state.get('ExitCode'), int),
            'container exit/OOM state')
    require(record.get('create', {}).get('returncode') == 0 and isinstance(record.get('attach_returncode'), int),
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
                payload: Path | None, copy_source: str | None, *, writable: bool = False) -> dict[str, Any]:
    command = DOCKER + ['create', '-i', '--name', name, '--read-only', '--network', 'none', '--cpus', '1',
                       '--memory', '512m', '--memory-swap', '512m', '--pids-limit', '32', '--mount',
                       'type=volume,source=sail-extension-targets,target=/targets' + (',readonly' if payload is None and not writable else ''),
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
                            and m.get('RW') is (payload is not None or writable) for m in item['Mounts']), 'small container ownership')
            limits = item['HostConfig']
            require(limits['NanoCpus'] == 10**9 and limits['Memory'] == 512 * 2**20
                    and limits['MemorySwap'] == 512 * 2**20 and limits['PidsLimit'] == 32
                    and limits['PidMode'] in ('', 'private') and limits['ReadonlyRootfs'] is True
                    and limits['NetworkMode'] == 'none', 'small private execution envelope')
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
    require(options.kind is not None and options.config is not None, 'run requires kind and config')
    assert options.config is not None
    raw = options.config.read_bytes()
    text = raw.decode('utf-8')
    config = json.loads(text)
    spec.update(kind=options.kind, run_id=options.run_id)
    parent = 'cells' if options.kind == 'cell' else 'references'
    output = ROOT + '/' + parent + '/' + options.run_id
    require(config.get('output') == output, 'configured fresh output tuple')
    for name in ('vertices', 'edges'):
        path = Path(config[name])
        require(path.is_absolute() and '..' not in path.parts and str(path).startswith('/targets/'), 'input path scope')
        require(not path.is_relative_to(Path(output)), 'inputs inside removable payload')
    if options.kind == 'cell':
        typed = CellConfiguration.model_validate_json(text)
        expected = {'repo': ROOT + '/repo', 'harness_repo': HARNESS_REPO, 'support': ROOT + '/support',
                    'binary': SAIL, 'support_sha256': spec['support_sha256']}
        require(all(config.get(key) == value for key, value in expected.items()), 'cell source/storage tuple')
        require(typed.references.is_relative_to(Path(ROOT) / 'references')
                and '..' not in typed.references.parts, 'reference path scope')
        require(typed.minimum_free_bytes == CAMPAIGN.guest_reserve_bytes, 'cell disk reserve tuple')
    else:
        require(set(config) == {'vertices', 'edges', 'output', 'vertices_sha256', 'edges_sha256'}, 'reference config fields')
        require(all(re.fullmatch(r'[a-f0-9]{64}', config[key]) is not None
                    for key in ('vertices_sha256', 'edges_sha256')), 'original input pins')
    with (host / 'helper-config.json').open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    spec.update(helper='supervise_shape.py' if options.kind == 'cell' else 'prepare_shapes.py', output=output,
                config_path=ROOT + '/configs/' + options.run_id + '.json', config_text=text,
                config_sha256=hashlib.sha256(raw).hexdigest(), vertices=config['vertices'], edges=config['edges'])
    return spec


def collected_inventory(directory: Path) -> dict[str, Any]:
    require(directory.is_dir() and not directory.is_symlink(), 'regular archive directory required')
    result: dict[str, Any] = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'collected symbolic link')
        if path.is_file():
            result[str(path.relative_to(directory))] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
        else:
            require(path.is_dir(), 'collected special file')
    require(bool(result), 'empty artifact collection')
    return result


def verify_archive(artifacts: Path) -> dict[str, Any]:
    inventory = collected_inventory(artifacts)
    manifest = json.loads((artifacts / 'archive-manifest.json').read_text())
    require(manifest.get('schema_version') == 1 and isinstance(manifest.get('files'), dict), 'guest archive manifest schema')
    actual = {name: identity for name, identity in inventory.items() if name != 'archive-manifest.json'}
    require(actual == manifest['files'], 'complete guest/host archive hash mismatch')
    return inventory


def producer_check(kind: Kind, artifacts: Path, spec: dict[str, Any]) -> dict[str, Any]:
    boot = json.loads((artifacts / 'bootstrap-receipt.json').read_text())
    require(boot.get('outcome') == 'passed' and boot.get('producer_returncode') == 0
            and boot.get('identities_before') == boot.get('identities_after')
            and boot.get('config_sha256') == spec.get('config_sha256'), 'bootstrap receipt did not pass')
    producer: dict[str, Any] = json.loads((artifacts / 'receipt.json').read_text())
    require(producer.get('outcome') == 'passed', 'producer did not pass')
    if kind == 'cell':
        effective = CellConfiguration.model_validate_json(spec['config_text']).model_dump(mode='json')
        require(producer.get('config') == effective, 'producer exact effective cell config')
        require(producer.get('identities_before') == producer.get('identities_after') and bool(producer.get('identities_before')),
                'producer identities changed/missing')
        require(producer.get('engine_returncode') == 0 and producer.get('engine_wait_completed') is True
                and producer.get('execution_verified') is True and producer.get('ownership_admitted') is True
                and not producer.get('outer_timeout')
                and not any(producer.get(key) for key in ('remaining_processes', 'remaining_after_cleanup', 'emergency_cleanup',
                                                         'observer_error', 'final_processes', 'finalization_errors', 'interruption_signals',
                                                         'preexisting_processes')),
                'producer execution/closure observations')
        correctness = producer.get('correctness') or {}
        require(correctness.get('outcome') == 'passed' and correctness.get('full_oracle') is True
                and correctness.get('shape') == producer['config']['shape']
                and correctness.get('rows') == correctness.get('expected_rows') == correctness.get('unique')
                and correctness.get('mismatches') == 0 and correctness.get('duplicate_rows') == 0
                and bool(correctness.get('result_files')) and bool(producer.get('plans'))
                and correctness.get('result_files') == correctness.get('result_files_after'),
                'full physical output/oracle/plans missing or failed')
        for name, identity in correctness['result_files'].items():
            relative = Path(name)
            require(not relative.is_absolute() and '..' not in relative.parts, 'result file scope')
            path = artifacts / 'engine/result' / relative
            require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'physical result hash')
        for name, identity in producer['plans'].items():
            require(re.fullmatch(r'engine/plan-[a-z0-9-]+\.txt', name) is not None, 'physical plan scope')
            path = artifacts / name
            require(path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'physical plan hash')
    else:
        require(producer.get('config') == json.loads(spec['config_text'])
                and producer.get('inputs_before') == producer.get('inputs_after') and bool(producer.get('inputs_before')),
                'reference original inputs/config changed')
        require(set(producer.get('artifacts', {})) == {'adjacency', 'representatives', 'min-label-initial-round'},
                'reference phase incomplete')
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
        receipt.observations['campaign'] = CAMPAIGN.model_dump(mode='json')
        receipt.observations['before'] = snapshot()
        save(host / 'result.json', receipt)
        spec = specification(pins)
        if options.action == 'stage':
            small = host / 'stage'
            small.mkdir()
            name = 'sem-review-b8-' + options.run_id + '-stage'
            record = owned_small(small, name, STAGE, spec, BASE / 'support/payload.tar', ROOT + '/stage-receipt.json')
            receipt.records['stage'] = record
            producer = json.loads((small / 'stage-receipt.json').read_text())
            require(producer.get('outcome') == 'passed', 'stage producer did not pass')
            receipt.producer_outcome = 'passed'
        else:
            spec = config_for(options, spec, host)
            outer_timeout = (CAMPAIGN.reference_timeout_seconds if options.kind == 'reference'
                             else CAMPAIGN.cell_timeout_seconds)
            save(host / 'configuration.json', {'specification': spec, 'config': matrix_config(),
                                             'guest_command': ['-I', '-B', '-c', BOOT, json.dumps(spec)],
                                             'outer_timeout_seconds': outer_timeout,
                                             'copy_timeout_adapter': {'frozen_seconds': 180,
                                                 'effective_seconds': CAMPAIGN.archive_copy_timeout_seconds,
                                                 'scope': 'Docker cp only; outside the engine timer'}})
            small = host / 'admission'
            small.mkdir()
            record = owned_small(small, 'sem-review-b8-' + options.run_id + '-admission', PROBE, spec, None, None)
            receipt.records['admission'] = record
            receipt.observations['guest_admission'] = json.loads(record['attach']['stdout'])
            save(host / 'result.json', receipt)
            matrix = matrix_module()
            name = 'sem-review-b8-' + options.run_id
            record = matrix_run(matrix, name, ['-I', '-B', '-c', BOOT, json.dumps(spec)],
                                host / 'container', spec['output'], outer_timeout)
            receipt.records['container'] = record
            save(host / 'container-record.json', record)
            check_matrix_record(record, name, True)
            receipt.certain_container_closure = True
            artifacts = host / 'container/artifacts'
            receipt.artifacts = verify_archive(artifacts)
            receipt.archive_verified = True
            save(host / 'collected-manifest.json', receipt.artifacts)
            receipt.producer_outcome = json.loads((artifacts / 'receipt.json').read_text()).get('outcome')
            save(host / 'result.json', receipt)
            assert options.kind is not None
            producer = producer_check(options.kind, artifacts, spec)
            receipt.producer_outcome = producer['outcome']
            require(record['inspect']['state']['ExitCode'] == 0 and record['attach_returncode'] == 0
                    and record['inspect']['state'].get('OOMKilled') is False, 'container producer exit/OOM')
            if options.kind == 'cell':
                remove = host / 'payload-removal'
                remove.mkdir()
                removal_spec = {**spec, 'archive_sha256': sha(artifacts / 'archive-manifest.json')}
                cleanup = owned_small(remove, 'sem-review-b8-' + options.run_id + '-remove', REMOVE, removal_spec,
                                      None, None, writable=True)
                receipt.records['payload_removal'] = cleanup
                removed = json.loads(cleanup['attach']['stdout'])
                require(removed.get('outcome') == 'passed' and removed.get('removed') == spec['output'], 'payload removal receipt')
                receipt.payload_removed = True
        receipt.certain_container_closure = True
        idle()
        receipt.observations['after'] = snapshot()
        require(host_pins() == pins, 'host helper/support identities changed')
        receipt.finished_utc = utc()
        receipt.outcome = 'passed'
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


def configure_campaign(path: Path) -> None:
    global BASE, ROOT, LOCK, CAMPAIGN
    campaign = Campaign.model_validate_json(path.read_text())
    require(campaign.host_root.is_absolute() and campaign.host_root.parent ==
            Path('/Volumes/Apo/graph-tests/results/sem-review-20261001')
            and re.fullmatch(r'B8-[A-Za-z0-9-]+', campaign.host_root.name) is not None, 'Apo campaign namespace')
    require(campaign.guest_root == '/targets/sem-review-20261001/' + campaign.host_root.name, 'matching guest campaign namespace')
    BASE, ROOT, CAMPAIGN = campaign.host_root, campaign.guest_root, campaign
    LOCK = BASE.parent / 'gate.lock'
    require(BASE.is_dir() and not BASE.is_symlink(), 'precreated regular host campaign directory required')


def arguments() -> Options:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'run'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--kind', choices=('reference', 'cell'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--campaign', type=Path, required=True)
    parsed = parser.parse_args()
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', parsed.run_id) is not None, 'safe unique run ID required')
    require((parsed.action == 'run') == (parsed.kind is not None), 'only run requires kind')
    require((parsed.action == 'run') == (parsed.config is not None), 'only run requires --config')
    return Options(parsed.action, parsed.run_id, parsed.kind, parsed.config, parsed.campaign)


if __name__ == '__main__':
    options = arguments()
    assert options.campaign is not None
    configure_campaign(options.campaign)
    sys.exit(execute(options))
