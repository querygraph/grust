"""Run an immutable B8 dataset queue; never retry, resume or clean engines.

CLI: --config QUEUE.json --dataset cit-Patents|graph500-24. QueueConfig pins
campaign/driver/plan/config-index/prerequisites/support. ConfigIndex.files maps
all60 run IDs to FilePins. Prerequisites pins stage, both full reference hosts,
and six closed tiny shape/variant hosts. host_proof() builds those metadata pins.
--write-plan PATH exclusively creates the60-step Plan before any execution.
Root stages and runs prerequisites; this helper starts only planned cell hosts.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Annotated, Any, Literal, Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import run_shapes_host as host_contract
import shape_reference
from pydantic import BaseModel, ConfigDict, Field, model_validator

Dataset = Literal['cit-Patents', 'graph500-24']
Shape = Literal['adjacency', 'representatives', 'min-label-initial-round']
Variant = Literal['union', 'array-explode']
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
RunId = Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')]
Json = dict[str, Any]
DATASETS: tuple[Dataset, ...] = ('cit-Patents', 'graph500-24')
SHAPES: tuple[Shape, ...] = ('adjacency', 'representatives', 'min-label-initial-round')
ORDER: tuple[Variant, ...] = ('union', 'array-explode', 'union', 'array-explode', 'array-explode',
                            'union', 'union', 'array-explode', 'array-explode', 'union')
DRIVER_SHA = 'ab2c33497e31df9b1f0010be78446df4eb936f09af4235264b6bb421e2f28e98'
COLUMNS: dict[Shape, list[str]] = {'adjacency': ['src', 'dst'], 'representatives': ['id', 'representative'],
                                  'min-label-initial-round': ['id', 'component']}
SOURCE: Literal['f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'] = 'f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'
HARNESS: Literal['6ae2e43a903c2cee02da170465c922c72b76198e'] = '6ae2e43a903c2cee02da170465c922c72b76198e'
RUNTIME: Literal['56194b170155301ba91077f0ba3df31fe2c78b6b'] = '56194b170155301ba91077f0ba3df31fe2c78b6b'
NATIVE: Literal['ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'] = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0)
    sha256: Digest


class FilePin(Identity):
    path: Path

    @model_validator(mode='after')
    def absolute(self) -> FilePin:
        require(self.path.is_absolute() and '..' not in self.path.parts, 'absolute clean pinned path')
        return self


class Step(Record):
    dataset: Dataset
    shape: Shape
    variant: Variant
    run_id: RunId
    role: Literal['warmup', 'measured']
    sequence_within_contrast: int
    measured_block: Literal[1, 2] | None


class Plan(Record):
    schema_version: Literal[1] = 1
    recorded_utc: str
    source: Literal['f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'] = SOURCE
    harness: Literal['6ae2e43a903c2cee02da170465c922c72b76198e'] = HARNESS
    runtime: Literal['56194b170155301ba91077f0ba3df31fe2c78b6b'] = RUNTIME
    native: Literal['ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'] = NATIVE
    image: str = host_contract.IMAGE
    matrix_sha256: str = host_contract.MATRIX_SHA
    cpus: Literal[16] = 16
    memory_bytes: Literal[34359738368] = 34359738368
    swap_bytes: Literal[0] = 0
    steps: list[Step]

    @model_validator(mode='after')
    def order(self) -> Plan:
        expected = [(dataset, shape, variant, index + 1, 'warmup' if index < 2 else 'measured',
                     None if index < 2 else 1 if index < 6 else 2)
                    for dataset in DATASETS for shape in SHAPES for index, variant in enumerate(ORDER)]
        actual = [(s.dataset, s.shape, s.variant, s.sequence_within_contrast, s.role, s.measured_block) for s in self.steps]
        require(actual == expected, 'exact60-step warmups+UA AU/UA AU plan required')
        require(len({s.run_id for s in self.steps}) == 60, 'unique planned IDs required')
        require(self.image == host_contract.IMAGE and self.matrix_sha256 == host_contract.MATRIX_SHA, 'image/matrix plan pins')
        return self


class ConfigIndex(Record):
    schema_version: Literal[1] = 1
    driver: FilePin
    campaign: FilePin
    plan: FilePin
    support_manifest: FilePin
    files: dict[str, FilePin]


class HostProof(Record):
    run_id: RunId
    directory: Path
    files: dict[str, Identity]


class TinyProof(HostProof):
    shape: Shape
    variant: Variant


class TinyInputs(Record):
    vertices: FilePin
    edges: FilePin


class DatasetContract(Record):
    vertices: Identity
    edges: Identity
    vertex_rows: int = Field(ge=1)
    edge_rows: int = Field(ge=1)
    evidence: FilePin


class Prerequisites(Record):
    schema_version: Literal[1] = 1
    stage: HostProof
    references: dict[Dataset, HostProof]
    datasets: dict[Dataset, DatasetContract]
    tiny_inputs: TinyInputs
    tiny_controls: list[TinyProof]


class QueueConfig(Record):
    host_root: Path
    output: Path
    python: Path
    driver: FilePin
    campaign: FilePin
    plan: FilePin
    config_index: FilePin
    prerequisites: FilePin
    support_manifest: FilePin

    @model_validator(mode='after')
    def paths(self) -> QueueConfig:
        for path in (self.host_root, self.output, self.python, self.driver.path, self.campaign.path, self.plan.path,
                     self.config_index.path, self.prerequisites.path, self.support_manifest.path):
            require(path.is_absolute() and '..' not in path.parts, 'absolute clean queue paths required')
        require(self.output.parent == self.host_root, 'queue output belongs directly to host campaign')
        return self


class CellProgress(Record):
    step: Step
    command: list[str]
    log: Path
    outcome: str = 'pending'
    started_utc: str | None = None
    finished_utc: str | None = None
    child_pid: int | None = None
    returncode: int | None = None
    audit: Json | None = None
    raw_receipts: Json = Field(default_factory=dict)


class Receipt(Record):
    schema_version: Literal[1] = 1
    config: QueueConfig
    dataset: Dataset
    owner_pid: int
    token: str
    started_utc: str
    observed_utc: str
    outcome: str = 'preparing'
    finished_utc: str | None = None
    active_child_pid: int | None = None
    lock_retained: bool = True
    pins: list[FilePin] = Field(default_factory=list)
    prerequisite_observations: Json = Field(default_factory=dict)
    cells: list[CellProgress] = Field(default_factory=list)
    interruption_signals: list[int] = Field(default_factory=list)
    error: str | None = None
    traceback: str | None = None
    ownership_scope: str = 'queue owns serial-queue.lock; host driver owns gate.lock/containers/engines; queue never sends cleanup signals'
    durability_scope: str = 'file fsync, atomic replace, directory fsync; macOS EINVAL/ENOTSUP tolerated without host power-loss qualification'


class Child(Protocol):
    pid: int
    def wait(self) -> int: ...
    def poll(self) -> int | None: ...


class Spawner(Protocol):
    def __call__(self, command: list[str], log: Path) -> Child: ...


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read(path: Path) -> Json:
    require(path.is_file() and not path.is_symlink(), 'regular JSON required: ' + str(path))
    data: Any = json.loads(path.read_bytes())
    require(isinstance(data, dict), 'JSON object required: ' + str(path))
    return cast(Json, data)


def pin(path: Path) -> FilePin:
    require(path.is_file() and not path.is_symlink(), 'regular pinned file required: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return FilePin(path=path, bytes=path.stat().st_size, sha256=digest)


def check_pin(expected: FilePin) -> None:
    require(pin(expected.path) == expected, 'immutable file changed: ' + str(expected.path))


def directory_fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if sys.platform != 'darwin' or error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(descriptor)


def save(path: Path, receipt: Receipt) -> None:
    receipt.observed_utc = utc()
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w') as stream:
        stream.write(receipt.model_dump_json(indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fsync(path.parent)


def build_plan() -> Plan:
    steps = [Step(dataset=dataset, shape=shape, variant=variant,
                  run_id=f'b8-{dataset.lower()}-{shape}-{index + 1:02d}-{variant}',
                  role='warmup' if index < 2 else 'measured', sequence_within_contrast=index + 1,
                  measured_block=None if index < 2 else 1 if index < 6 else 2)
             for dataset in DATASETS for shape in SHAPES for index, variant in enumerate(ORDER)]
    return Plan(recorded_utc=utc(), steps=steps)


def host_proof(directory: Path, kind: Literal['stage', 'reference', 'cell']) -> HostProof:
    names = ['result.json', 'support-identities.json']
    names += (['stage/orchestration.json', 'stage/stage-receipt.json'] if kind == 'stage' else
              ['configuration.json', 'helper-config.json', 'container-record.json', 'collected-manifest.json',
               'container/artifacts/receipt.json', 'container/artifacts/bootstrap-receipt.json',
               'container/artifacts/archive-manifest.json'])
    if kind == 'cell':
        names += ['payload-removal/orchestration.json']
    return HostProof(run_id=directory.name, directory=directory,
        files={name: Identity(bytes=(p := pin(directory/name)).bytes, sha256=p.sha256) for name in names})


def proof_files(proof: HostProof, config: QueueConfig, receipt: Receipt, kind: Literal['stage', 'reference', 'cell']) -> None:
    require(proof.directory == config.host_root / proof.run_id, 'prerequisite host scope')
    require(set(proof.files) == set(host_proof(proof.directory, kind).files), 'complete prerequisite metadata file set')
    for name, expected in proof.files.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'prerequisite file scope')
        actual = pin(proof.directory/relative)
        require(actual.bytes == expected.bytes and actual.sha256 == expected.sha256, 'prerequisite receipt pin: ' + name)
        receipt.pins.append(actual)


def host_closed(host: Json, run_id: str, kind: str) -> None:
    require(host.get('run_id') == run_id and host.get('action') == ('stage' if kind == 'stage' else 'run')
            and host.get('kind') == (None if kind == 'stage' else kind), 'host identity/kind')
    require(host.get('outcome') == 'passed' and bool(host.get('finished_utc')) and host.get('certain_container_closure') is True
            and host.get('lock_retained') is False and not host.get('error') and not host.get('traceback'), 'host finalized closure')
    if kind != 'stage':
        require(host.get('archive_verified') is True and host.get('producer_outcome') == 'passed', 'verified producer archive')
    if kind == 'cell':
        require(host.get('payload_removed') is True, 'passed cell payload not removed')


def no_oom(cgroups: Json) -> None:
    require(set(cgroups) >= {'before', 'after_engine', 'after_oracle', 'final'}, 'complete cgroup phases required')
    for snapshot in cgroups.values():
        require(snapshot.get('cpu.max') == '1600000 100000' and snapshot.get('memory.max') == str(32*2**30)
                and snapshot.get('memory.swap.max') == '0', 'private16CPU/32GiB/no-swap cgroup')
        events = snapshot.get('memory.events')
        require(isinstance(events, str), 'missing cgroup OOM events')
        parsed = {key: int(value) for key, value in (line.split() for line in events.splitlines())}
        require(parsed.get('oom') == 0 and parsed.get('oom_kill') == 0, 'cgroup OOM observation')


def closed_container(record: Json) -> None:
    inspection = record.get('inspect') or {}
    state = inspection.get('state') or {}
    require(record.get('create', {}).get('returncode') == 0 and record.get('attach_returncode') == 0
            and record.get('remove', {}).get('returncode') == 0
            and record.get('copied', {}).get('artifacts', {}).get('returncode') == 0
            and inspection.get('image') == host_contract.IMAGE
            and inspection.get('id') == record.get('create', {}).get('stdout', '').strip(), 'owned container identity/copy/exit')
    require(state.get('Running') is False and state.get('ExitCode') == 0 and state.get('OOMKilled') is False and not state.get('Error')
            and not any(record.get(key) for key in ('transport_errors', 'kill', 'forced_cleanup_kill', 'outer_timeout', 'operator_interrupted')),
            'container closure/transport')
    limits = inspection.get('limits') or {}
    require(limits.get('NanoCpus') == 16*10**9 and limits.get('CpusetCpus') == '0-15'
            and limits.get('Memory') == limits.get('MemorySwap') == 32*2**30 and limits.get('Init') is True
            and limits.get('PidMode') in ('', 'private') and limits.get('PidsLimit') == 1024, 'observed container envelope')
    require(re.fullmatch(r'[a-f0-9]{64}', inspection.get('id', '')) is not None, 'owned container ID')
    absence(record)


def absence(record: Json) -> None:
    observed = record.get('absence_verified') or {}
    stderr = observed.get('stderr', '').lower()
    require(observed.get('returncode') == 1 and ('no such object' in stderr or 'no such container' in stderr), 'owned container absence evidence')


def small_closed(record: Json) -> None:
    item = record.get('inspect') or {}
    state = item.get('State') or {}
    require(record.get('certain_closure') is True and record.get('ownership_verified') is True
            and not record.get('errors') and not record.get('kill')
            and record.get('attach', {}).get('returncode') == 0
            and record.get('remove', {}).get('returncode') == 0
            and item.get('Id') == record.get('create', {}).get('stdout', '').strip()
            and record.get('create', {}).get('returncode') == 0
            and item.get('Image') == host_contract.IMAGE and state.get('Running') is False
            and state.get('ExitCode') == 0 and state.get('OOMKilled') is False and not state.get('Error'), 'owned small container clean closure')
    limits = item.get('HostConfig') or {}
    require(limits.get('NanoCpus') == 10**9 and limits.get('Memory') == limits.get('MemorySwap') == 512*2**20
            and limits.get('PidsLimit') == 32 and limits.get('PidMode') in ('', 'private')
            and limits.get('ReadonlyRootfs') is True and limits.get('NetworkMode') == 'none', 'small private envelope')
    absence(record)


def physical_archive(directory: Path, host: Json) -> Json:
    artifacts = directory/'container/artifacts'
    guest = read(artifacts/'archive-manifest.json')
    require(guest.get('schema_version') == 1 and isinstance(guest.get('files'), dict), 'complete guest archive manifest')
    actual = host_contract.collected_inventory(artifacts)
    require({name: value for name, value in actual.items() if name != 'archive-manifest.json'} == guest['files']
            and actual == host.get('artifacts') and actual == read(directory/'collected-manifest.json'), 'complete raw archive hash/set binding')
    return actual


def actual_method(shape: Shape, variant: Variant) -> str:
    if shape == 'min-label-initial-round':
        return 'min-label-whole-update-left-join-array-explode' if variant == 'array-explode' else 'min-label-labels-union-messages'
    return shape+'-'+variant


def raw_receipts(directory: Path) -> Json:
    paths = {'host': directory/'result.json', 'container': directory/'container-record.json',
             'producer': directory/'container/artifacts/receipt.json', 'bootstrap': directory/'container/artifacts/bootstrap-receipt.json',
             'engine': directory/'container/artifacts/engine/engine-receipt.json'}
    return {name: read(path) for name, path in paths.items() if path.is_file()}


def support_binding(directory: Path, config: QueueConfig, campaign: host_contract.Campaign) -> Json:
    host, support = read(directory/'result.json'), read(directory/'support-identities.json')
    require(host.get('observations', {}).get('campaign') == campaign.model_dump(mode='json'), 'archived campaign differs')
    require(support.get('wrapper_sha256') == config.driver.sha256 == DRIVER_SHA
            and support.get('matrix_sha256') == host_contract.MATRIX_SHA
            and support.get('support_sha256') == config.support_manifest.sha256
            and support.get('support') == read(config.support_manifest.path), 'archived helper/source support binding')
    return support


def audited_archive(directory: Path, run_id: str, kind: Literal['reference', 'cell'],
                    config: QueueConfig, campaign: host_contract.Campaign) -> tuple[Json, Json, Json]:
    host = read(directory/'result.json')
    host_closed(host, run_id, kind)
    record = read(directory/'container-record.json')
    require(host.get('records', {}).get('container') == record, 'embedded/separate container records differ')
    closed_container(record)
    small_closed(host['records']['admission'])
    archive = physical_archive(directory, host)
    support_binding(directory, config, campaign)
    spec = read(directory/'configuration.json')['specification']
    helper_pin = pin(directory/'helper-config.json')
    require(spec.get('config_sha256') == helper_pin.sha256 and spec.get('config_text', '').encode() == helper_pin.path.read_bytes()
            and spec.get('run_id') == run_id and spec.get('kind') == kind
            and spec.get('controller') == SOURCE and spec.get('harness') == HARNESS
            and spec.get('root') == campaign.guest_root and spec.get('harness_repo') == host_contract.HARNESS_REPO
            and spec.get('sail') == host_contract.SAIL and spec.get('sail_sha256') == host_contract.SAIL_SHA
            and spec.get('native_sha256') == host_contract.NATIVE_SHA
            and spec.get('support_sha256') == config.support_manifest.sha256, 'archived launch config/source binding')
    boot = read(directory/'container/artifacts/bootstrap-receipt.json')
    require(boot.get('outcome') == 'passed' and bool(boot.get('finished_utc')) and boot.get('producer_returncode') == 0
            and boot.get('kind') == kind and boot.get('config_sha256') == helper_pin.sha256
            and bool(boot.get('identities_before')) and boot.get('identities_before') == boot.get('identities_after')
            and not any(boot.get(k) for k in ('error', 'traceback', 'final_guard_traceback')), 'bootstrap identities/exit/config')
    return host, archive, spec


def audit_reference(proof: HostProof, config: QueueConfig, campaign: host_contract.Campaign) -> Json:
    _, archive, _ = audited_archive(proof.directory, proof.run_id, 'reference', config, campaign)
    raw = read(proof.directory/'container/artifacts/receipt.json')
    reference = shape_reference.ReferenceReceipt.model_validate(raw)
    require(reference.outcome == 'passed' and bool(reference.finished_utc) and not reference.error
            and reference.inputs_before is not None and reference.inputs_before == reference.inputs_after,
            'reference finalized unchanged inputs')
    require(reference.config.model_dump(mode='json') == read(proof.directory/'helper-config.json')
            and reference.config.output == Path(campaign.guest_root)/'references'/proof.run_id,
            'reference config/output tuple')
    assert reference.inputs_before is not None
    require(reference.inputs_before.vertices.sha256 == reference.config.vertices_sha256
            and reference.inputs_before.edges.sha256 == reference.config.edges_sha256
            and set(reference.artifacts) == set(SHAPES) and reference.vertex_rows is not None
            and reference.edge_rows is not None and reference.isolated_vertices is not None, 'complete reference input/count pins')
    for shape, artifact in reference.artifacts.items():
        require(artifact.file == shape+'.i64le' and artifact.columns == COLUMNS[shape]
                and artifact.identity.bytes == 16*artifact.rows
                and artifact.identity.model_dump(mode='json') == archive.get(artifact.file), 'complete physical reference identity')
    support = read(config.support_manifest.path)['files_sha256']
    require(set(reference.helper_sha256) == {'prepare_shapes.py', 'shape_reference.py'}
            and all(support.get(name) == value for name, value in reference.helper_sha256.items()), 'reference helper source pins')
    return raw


def audit_cell(step: Step, config: QueueConfig, campaign: host_contract.Campaign,
               effective: host_contract.CellConfiguration, reference: Json) -> Json:
    directory = config.host_root/step.run_id
    host, archive, _ = audited_archive(directory, step.run_id, 'cell', config, campaign)
    artifacts = directory/'container/artifacts'
    producer, engine = read(artifacts/'receipt.json'), read(artifacts/'engine/engine-receipt.json')
    expected_paths = {'repo': campaign.guest_root+'/repo', 'harness_repo': host_contract.HARNESS_REPO,
        'support': campaign.guest_root+'/support', 'output': campaign.guest_root+'/cells/'+step.run_id,
        'binary': host_contract.SAIL, 'support_sha256': config.support_manifest.sha256,
        'minimum_free_bytes': campaign.guest_reserve_bytes}
    require(all(effective.model_dump(mode='json').get(name) == value for name, value in expected_paths.items())
            and effective.references == Path(campaign.guest_root)/'references'/effective.references.name,
            'actual cell source/owned output/reference/disk tuple')
    require(host_contract.CellConfiguration.model_validate(read(directory/'helper-config.json')) == effective
            and producer.get('config') == effective.model_dump(mode='json'), 'actual exact effective cell configuration')
    require(producer.get('outcome') == 'passed' and bool(producer.get('finished_utc'))
            and producer.get('error') is None and producer.get('traceback') is None
            and producer.get('engine_returncode') == 0 and producer.get('engine_wait_completed') is True
            and producer.get('execution_verified') is True and producer.get('ownership_admitted') is True
            and not any(producer.get(k) for k in ('outer_timeout', 'remaining_processes', 'remaining_after_cleanup',
                'emergency_cleanup', 'observer_error', 'final_processes', 'finalization_errors', 'interruption_signals',
                'preexisting_processes')), 'engine wait/ownership/cleanup/finalization')
    elapsed = producer.get('launch_to_exit_seconds')
    require(isinstance(elapsed, (float, int)) and math.isfinite(elapsed) and elapsed > 0
            and producer.get('sampled_engine_pss_peak_bytes', 0) > 0 and producer.get('sampled_engine_pss_rows', 0) > 0
            and producer.get('sampled_engine_rows', 0) > 0 and producer.get('memory', {}).get('execution_sampled') is True
            and archive.get('memory-samples.jsonl', {}).get('bytes', 0) > 0, 'positive measured timer/owned engine PSS sample')
    identities = producer.get('identities_before') or {}
    require(bool(identities) and identities == producer.get('identities_after') and identities.get('controller') == SOURCE
            and identities.get('harness') == HARNESS and identities.get('binary') == host_contract.SAIL_SHA
            and identities.get('support') == read(config.support_manifest.path) and identities.get('reference_phase') == reference
            and host_contract.NATIVE_SHA in identities.get('native', {}).get('files_sha256', {}).values(), 'actual before/after input/reference/helper/binary source identities')
    no_oom(producer.get('cgroups') or {})
    require(producer.get('engine_receipt') == engine and engine.get('outcome') == 'passed' and bool(engine.get('finished_utc'))
            and engine.get('result_exported') is True and not any(engine.get(k) for k in ('cleanup_errors', 'staging_payload_after_shutdown', 'error'))
            and engine.get('controller_pin') == SOURCE and engine.get('runtime_pin') == RUNTIME and engine.get('native_pin') == NATIVE
            and producer.get('actual_engine_method') == engine.get('actual_method') == actual_method(step.shape, step.variant),
            'actual engine receipt/method/pins/export/cleanup')
    engine_config = {'repo': str(effective.repo), 'harness_repo': str(effective.harness_repo), 'output': str(effective.output/'engine'),
        'vertices': str(effective.vertices), 'edges': str(effective.edges), 'binary': str(effective.binary), 'mode': 'local',
        'partitions': 16, 'pool_bytes': 30*2**30, 'native_quota': 256*2**20, 'shape': step.shape, 'variant': step.variant}
    require(engine.get('config') == read(artifacts/'engine-config.json') == engine_config
            and producer.get('command') == [host_contract.PYTHON, '-B', str(effective.support/'engine_shapes.py'),
                                           '--config', str(effective.output/'engine-config.json')], 'actual child module/config/resource envelope')
    origins = engine.get('origins') or {}
    package, benchmark = effective.repo/'examples/extensions/graph-algorithms/src/pyspark_pecan', effective.harness_repo/'examples/extensions/benchmarks'
    require(all(origins.get(key) == str(path) for key, path in {'algorithms': package/'algorithms.py',
            'wcc_randomized': package/'wcc_randomized.py', 'runtime': benchmark/'runtime.py', 'measurement': benchmark/'measurement.py'}.items())
            and origins.get('python_executable') == host_contract.PYTHON
            and engine.get('output_projection') == COLUMNS[step.shape]
            and [(field.get('name'), field.get('type')) for field in engine.get('output_schema', [])] == [(n, 'bigint') for n in COLUMNS[step.shape]],
            'raw engine field types/module origins')
    correctness = producer.get('correctness') or {}
    expected = reference['artifacts'][step.shape]
    reference_receipt = pin(config.host_root/effective.references.name/'container/artifacts/receipt.json')
    require(reference_receipt.sha256 == effective.reference_receipt_sha256 and read(reference_receipt.path) == reference,
            'sealed selected reference receipt bytes')
    # The reference receipt bytes are pinned by the config and outside the copied cell directory.
    require(correctness.get('outcome') == 'passed' and correctness.get('full_oracle') is True
            and correctness.get('shape') == step.shape and correctness.get('rows') == correctness.get('unique') == correctness.get('expected_rows') == expected['rows']
            and correctness.get('mismatches') == 0 and correctness.get('duplicate_rows') == 0
            and correctness.get('reference_artifact') == expected
            and correctness.get('reference_receipt') == {'bytes': reference_receipt.bytes, 'sha256': reference_receipt.sha256},
            'complete exact physical oracle/reference cardinality')
    files = correctness.get('result_files') or {}
    require(bool(files) and files == correctness.get('result_files_after'), 'unchanged full raw output file identities')
    for name, identity in files.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and archive.get('engine/result/'+name) == identity, 'result physical archive identity')
    schemas = correctness.get('physical_schemas') or []
    require(bool(schemas) and {s['file'] for s in schemas} == {name for name in files if name.endswith('.parquet')}
            and all([(f['name'], f['arrow_type']) for f in s['fields']] == [(n, 'int64') for n in COLUMNS[step.shape]] for s in schemas),
            'physical footer rows/raw named field types')
    relations = ['initial-adjacency', 'initial-labels', 'shape-result'] if step.shape == 'min-label-initial-round' else ['shape-result']
    plans = producer.get('plans') or {}
    require([p.get('relation') for p in engine.get('plans', [])] == relations
            and set(plans) == {'engine/plan-'+name+'.txt' for name in relations}, 'raw plan exact relation/file set')
    for plan in engine['plans']:
        name = 'engine/'+plan['file']
        identity = plans[name]
        require(plan['file'] == 'plan-'+plan['relation']+'.txt' and identity.get('relation') == plan['relation']
                and identity.get('scope') == plan['scope'] and {k: identity[k] for k in ('bytes', 'sha256')} == archive[name], 'actual raw plan binding')
    removal = host['records']['payload_removal']
    require(removal == read(directory/'payload-removal/orchestration.json'), 'embedded/separate payload removal records differ')
    small_closed(removal)
    removed: Any = json.loads(removal['attach']['stdout'])
    require(isinstance(removed, dict) and removed.get('outcome') == 'passed' and removed.get('removed') == str(effective.output)
            and removed.get('archive_sha256') == archive['archive-manifest.json']['sha256'], 'owned archive-bound payload removal')
    return {'qualified': True, 'run_id': step.run_id, 'role': step.role, 'dataset': effective.dataset, 'shape': step.shape,
        'variant': step.variant, 'actual_method': engine['actual_method'], 'launch_to_exit_seconds': elapsed,
        'sampled_engine_pss_peak_bytes': producer['sampled_engine_pss_peak_bytes'], 'guest_steal_fraction': producer.get('guest_steal_fraction'),
        'rows': expected['rows'], 'result_files': files, 'plans': plans, 'scope': 'isolated paired relational shape on shared host; not a full algorithm'}


def tiny_observations(inputs: TinyInputs) -> Json:
    """Inspect only bounded tiny original bytes; full inputs use sealed references."""
    columns: list[list[int]] = []
    for expected, names, maximum in ((inputs.vertices, ['id'], 4096), (inputs.edges, ['source', 'target'], 16384)):
        check_pin(expected)
        require(expected.bytes <= 16*2**20, 'tiny inspection refuses large original file')
        with pq.ParquetFile(expected.path) as parquet:
            require(parquet.metadata.num_rows <= maximum and parquet.schema_arrow.names == names
                    and all(f.type == pa.int64() for f in parquet.schema_arrow), 'bounded tiny physical signed64 input schema')
            table = parquet.read(use_threads=False)
            require(all(c.null_count == 0 for c in table.columns), 'tiny input NULL')
            columns.extend([cast(list[int], c.to_pylist()) for c in table.columns])
        check_pin(expected)
    ids, sources, targets = columns
    members = set(ids)
    edges = list(zip(sources, targets, strict=True))
    require(len(members) == len(ids) and set(sources+targets) <= members, 'tiny unique IDs/endpoints')
    isolated = members-set(sources+targets)
    negative = [value for value in ids if value < 0]
    high_magnitude = [value for value in ids if abs(value) > 2**53]
    require(bool(negative) and bool(high_magnitude) and len(set(edges)) < len(edges)
            and any(u == v for u, v in edges) and bool(isolated), 'tiny signed/highbit/duplicate/loop/isolate witness required')
    return {'vertex_rows': len(ids), 'edge_rows': len(edges), 'signed_negative_ids': [str(n) for n in negative],
        'high_magnitude_ids': [str(n) for n in high_magnitude], 'duplicate_edges': len(edges)-len(set(edges)),
        'self_loops': sum(u == v for u, v in edges), 'isolated_vertices': len(isolated),
        'isolated_ids': [str(n) for n in sorted(isolated)], 'scope': 'observed bounded original tiny Parquet bytes only'}


def dataset_binding(dataset: Dataset, contract: DatasetContract, reference: Json) -> None:
    check_pin(contract.evidence)
    evidence = read(contract.evidence.path)
    originals = {'vertices': contract.vertices.model_dump(mode='json'), 'edges': contract.edges.model_dump(mode='json')}
    require(reference.get('inputs_before') == originals and reference.get('vertex_rows') == contract.vertex_rows
            and reference.get('edge_rows') == contract.edge_rows, 'dataset independent original identity/count binding')
    if dataset == 'cit-Patents':
        require(contract.vertices.sha256 == '0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa'
                and contract.edges.sha256 == '70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f'
                and contract.vertex_rows == 3774768 and contract.edge_rows == 16518947
                and evidence.get('outcome') == 'passed' and evidence.get('originals_before') == evidence.get('originals_after')
                and all(evidence.get('originals_before', {}).get(k) == v for k, v in originals.items())
                and evidence.get('validation', {}).get('vertex_rows') == contract.vertex_rows
                and evidence.get('validation', {}).get('edge_rows') == contract.edge_rows, 'pinned cit-Patents original validation contract')
    else:
        expected_urls = {'vertices.parquet': 'https://datasets.ldbcouncil.org/graphalytics-parquet/graph500-24-v.parquet',
                         'edges.parquet': 'https://datasets.ldbcouncil.org/graphalytics-parquet/graph500-24-e.parquet'}
        require(evidence.get('outcome') == 'downloaded_and_admitted' and bool(evidence.get('finished_utc'))
                and not evidence.get('error') and evidence.get('urls') == expected_urls
                and evidence.get('files') == {name+'.parquet': value for name, value in originals.items()}
                and evidence.get('admission', {}).get('vertex_rows') == contract.vertex_rows
                and evidence.get('admission', {}).get('edge_rows') == contract.edge_rows, 'actual Graph500-24 downloaded payload SHA/footer admission required')


def prerequisite_audits(config: QueueConfig, receipt: Receipt, campaign: host_contract.Campaign) -> dict[Dataset, Json]:
    prerequisites = Prerequisites.model_validate(read(config.prerequisites.path))
    require(set(prerequisites.references) == set(prerequisites.datasets) == set(DATASETS)
            and {(p.shape, p.variant) for p in prerequisites.tiny_controls} == {(s, v) for s in SHAPES for v in ('union', 'array-explode')}
            and len(prerequisites.tiny_controls) == 6, 'both full references and exact six tiny paired controls required')
    proofs = [prerequisites.stage, *prerequisites.references.values(), *prerequisites.tiny_controls]
    require(len({p.run_id for p in proofs}) == len(proofs), 'unique prerequisite host IDs')
    stage = prerequisites.stage
    proof_files(stage, config, receipt, 'stage')
    stage_host = read(stage.directory/'result.json')
    host_closed(stage_host, stage.run_id, 'stage')
    support_binding(stage.directory, config, campaign)
    stage_record = read(stage.directory/'stage/orchestration.json')
    require(stage_record == stage_host['records']['stage'], 'stage raw host record binding')
    small_closed(stage_record)
    stage_producer = read(stage.directory/'stage/stage-receipt.json')
    before, after = stage_producer.get('identities_before') or {}, stage_producer.get('identities_after') or {}
    require(stage_producer.get('outcome') == 'passed' and not stage_producer.get('error')
            and before.get('binary') == after.get('binary') == {'sail': host_contract.SAIL_SHA}
            and after.get('controller') == SOURCE and after.get('harness') == HARNESS
            and after.get('support') == read(config.support_manifest.path), 'staged source/helper/binary identity')
    references: dict[Dataset, Json] = {}
    for dataset, proof in prerequisites.references.items():
        proof_files(proof, config, receipt, 'reference')
        references[dataset] = audit_reference(proof, config, campaign)
        contract = prerequisites.datasets[dataset]
        dataset_binding(dataset, contract, references[dataset])
        receipt.pins.append(contract.evidence)
    for original in (prerequisites.tiny_inputs.vertices, prerequisites.tiny_inputs.edges):
        check_pin(original)
        receipt.pins.append(original)
    observed = tiny_observations(prerequisites.tiny_inputs)
    common: Json | None = None
    tiny_audits: list[Json] = []
    for proof in prerequisites.tiny_controls:
        proof_files(proof, config, receipt, 'cell')
        effective = host_contract.CellConfiguration.model_validate(read(proof.directory/'helper-config.json'))
        require(effective.shape == proof.shape and effective.variant == proof.variant, 'tiny proof actual shape/variant')
        reference_directory = config.host_root/effective.references.name
        tiny_reference_proof = host_proof(reference_directory, 'reference')
        proof_files(tiny_reference_proof, config, receipt, 'reference')
        require(tiny_reference_proof.files['container/artifacts/receipt.json'].sha256 == effective.reference_receipt_sha256,
                'tiny exact reference receipt bytes')
        tiny_reference = audit_reference(tiny_reference_proof, config, campaign)
        require(common is None or common == tiny_reference, 'paired tiny controls must share exact input/reference bytes')
        common = tiny_reference
        expected_inputs = {name: {'bytes': value.bytes, 'sha256': value.sha256} for name, value in
            (('vertices', prerequisites.tiny_inputs.vertices), ('edges', prerequisites.tiny_inputs.edges))}
        require(tiny_reference.get('inputs_before') == expected_inputs
                and tiny_reference.get('isolated_vertices') == observed['isolated_vertices'], 'tiny inspected original/reference binding')
        tiny_step = Step(dataset='cit-Patents', shape=proof.shape, variant=proof.variant, run_id=proof.run_id,
                         role='warmup', sequence_within_contrast=0, measured_block=None)
        tiny_audits.append(audit_cell(tiny_step, config, campaign, effective, tiny_reference))
    receipt.prerequisite_observations = {'stage': stage_producer, 'references': references,
        'dataset_contracts': {k: v.model_dump(mode='json') for k, v in prerequisites.datasets.items()},
        'tiny_inputs': observed, 'tiny_controls': tiny_audits, 'tiny_reference': common}
    return references


def unoccupied(base: Path, run_id: str) -> None:
    require(not (base/run_id).exists() and not (base/run_id).is_symlink(), 'existing run directory; no retries: '+run_id)
    require(not list(base.glob(run_id+'*.log')) and not list(base.glob(run_id+'*.launch.json')), 'existing run log/launch receipt; no retries: '+run_id)


def prepare(config: QueueConfig, dataset: Dataset, receipt: Receipt) -> tuple[host_contract.Campaign, dict[str, host_contract.CellConfiguration], dict[Dataset, Json]]:
    loaded_driver = pin(Path(host_contract.__file__).resolve())
    require(config.driver.sha256 == loaded_driver.sha256 == DRIVER_SHA, 'frozen child and loaded host driver identity')
    receipt.pins.extend([pin(Path(__file__).resolve()), loaded_driver])
    for name in ('driver', 'campaign', 'plan', 'config_index', 'prerequisites', 'support_manifest'):
        expected = cast(FilePin, getattr(config, name))
        check_pin(expected)
        receipt.pins.append(expected)
    campaign = host_contract.Campaign.model_validate(read(config.campaign.path))
    require(campaign.host_root == config.host_root, 'campaign/queue host scope')
    support = read(config.support_manifest.path)
    files = support.get('files_sha256') or {}
    require(support.get('schema_version') == 1 and set(files) >= {'engine_shapes.py', 'supervise_shape.py', 'prepare_shapes.py', 'shape_reference.py', 'shape_oracle.py'}, 'complete frozen support helpers')
    for name, sha in files.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) is not None, 'support basename scope')
        actual = pin(config.support_manifest.path.parent/name)
        require(actual.sha256 == sha, 'host helper identity: '+name)
        receipt.pins.append(actual)
    require(pin(Path(__file__).resolve()).sha256 == files.get('run_pair_queue.py'), 'executed queue matches committed support bytes')
    plan = Plan.model_validate(read(config.plan.path))
    index = ConfigIndex.model_validate(read(config.config_index.path))
    require(all(getattr(index, key) == getattr(config, key) for key in ('driver', 'campaign', 'plan', 'support_manifest'))
            and set(index.files) == {step.run_id for step in plan.steps}, 'complete immutable manifest/plan bindings')
    references = prerequisite_audits(config, receipt, campaign)
    proofs = Prerequisites.model_validate(read(config.prerequisites.path)).references
    cells: dict[str, host_contract.CellConfiguration] = {}
    for step in plan.steps:
        expected = index.files[step.run_id]
        check_pin(expected)
        receipt.pins.append(expected)
        effective = host_contract.CellConfiguration.model_validate(read(expected.path))
        reference = references[step.dataset]
        reference_sha = proofs[step.dataset].files['container/artifacts/receipt.json'].sha256
        required = {'dataset': step.dataset, 'shape': step.shape, 'variant': step.variant,
            'repo': campaign.guest_root+'/repo', 'harness_repo': host_contract.HARNESS_REPO,
            'support': campaign.guest_root+'/support', 'output': campaign.guest_root+'/cells/'+step.run_id,
            'binary': host_contract.SAIL, 'references': reference['config']['output'],
            'vertices': reference['config']['vertices'], 'edges': reference['config']['edges'],
            'minimum_free_bytes': campaign.guest_reserve_bytes, 'reference_receipt_sha256': reference_sha,
            'support_sha256': config.support_manifest.sha256}
        actual_config = effective.model_dump(mode='json')
        require(all(actual_config.get(name) == value for name, value in required.items()), 'planned exact source/dataset/input/reference/config tuple: '+step.run_id)
        if step.dataset != dataset:
            continue
        unoccupied(config.host_root, step.run_id)
        command = [str(config.python), '-B', str(config.driver.path), 'run', '--campaign', str(config.campaign.path),
                   '--run-id', step.run_id, '--kind', 'cell', '--config', str(expected.path)]
        cells[step.run_id] = effective
        receipt.cells.append(CellProgress(step=step, command=command, log=config.host_root/(step.run_id+'.host.log')))
    require(len(cells) == 30, 'exact30 selected cells required')
    return campaign, cells, references


def verify_pins(receipt: Receipt) -> None:
    for expected in receipt.pins:
        check_pin(expected)


def spawn(command: list[str], log: Path) -> Child:
    with log.open('xb') as stream:
        directory_fsync(log.parent)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    return process


def run(config_path: Path, dataset: Dataset, spawner: Spawner = spawn) -> int:
    config = QueueConfig.model_validate(read(config_path))
    gate, lock = config.host_root.parent/'gate.lock', config.host_root.parent/'serial-queue.lock'
    require(config.host_root.is_dir() and not config.host_root.is_symlink()
            and not config.output.exists() and not config.output.is_symlink(), 'fresh queue namespace required; no resume')
    require(not gate.exists() and not gate.is_symlink(), 'global gate.lock present; phase overlap refused')
    receipt = Receipt(config=config, dataset=dataset, owner_pid=os.getpid(), token=uuid.uuid4().hex, started_utc=utc(), observed_utc=utc())
    receipt_path, owner_path = config.output/'receipt.json', lock/'owner.json'
    lock.mkdir(exist_ok=False)
    child: Child | None = None
    progress: CellProgress | None = None
    previous: dict[int, Any] = {}
    closing = False

    def interrupted(signum: int, _frame: FrameType | None) -> None:
        receipt.interruption_signals.append(signum)
        if not closing:
            raise InterruptedError('queue interrupted; child cleanup remains host responsibility')

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupted)
        save(owner_path, receipt)
        directory_fsync(lock.parent)
        config.output.mkdir(exist_ok=False)
        directory_fsync(config.output.parent)
        receipt.pins.append(pin(config_path))
        save(receipt_path, receipt)
        campaign, effective, references = prepare(config, dataset, receipt)
        receipt.outcome = 'running'
        save(receipt_path, receipt)
        for progress in receipt.cells:
            require(child is None, 'serial queue child overlap')
            verify_pins(receipt)
            require(not gate.exists() and not gate.is_symlink(), 'global gate.lock appeared before cell')
            unoccupied(config.host_root, progress.step.run_id)
            progress.started_utc, progress.outcome = utc(), 'launch_intent'
            save(receipt_path, receipt)
            child = spawner(progress.command, progress.log)
            progress.child_pid, receipt.active_child_pid, progress.outcome = child.pid, child.pid, 'running'
            save(receipt_path, receipt)
            progress.returncode = child.wait()
            progress.finished_utc, progress.outcome = utc(), 'child_exited'
            receipt.active_child_pid = None
            progress.raw_receipts = raw_receipts(config.host_root/progress.step.run_id)
            save(receipt_path, receipt)
            require(progress.returncode == 0, 'host child exit failed: '+progress.step.run_id)
            require(not gate.exists() and not gate.is_symlink(), 'global gate.lock retained after cell')
            progress.audit = audit_cell(progress.step, config, campaign, effective[progress.step.run_id], references[dataset])
            verify_pins(receipt)
            progress.outcome = 'passed'
            child = None
            save(receipt_path, receipt)
        verify_pins(receipt)
        owner = read(owner_path)
        require(owner.get('token') == receipt.token and owner.get('owner_pid') == os.getpid()
                and {p.name for p in lock.iterdir()} == {'owner.json'}, 'queue lock ownership changed')
        require(not gate.exists() and not gate.is_symlink(), 'global gate.lock appeared at queue close')
        receipt.outcome, receipt.finished_utc = 'passed', utc()
        save(receipt_path, receipt)
        owner_path.unlink()
        lock.rmdir()
        directory_fsync(lock.parent)
        receipt.lock_retained = False
        save(receipt_path, receipt)
        return 0
    except BaseException as error:  # noqa: BLE001 - preserve interruption/failure and retained ownership without cleaning engines.
        closing = True
        receipt.outcome = 'interrupted' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'error'
        receipt.error, receipt.traceback, receipt.finished_utc = repr(error), traceback.format_exc(), utc()
        receipt.lock_retained = lock.exists()
        if child is not None:
            try:
                code = child.poll()
                receipt.active_child_pid = child.pid if code is None else None
                if progress is not None:
                    progress.returncode = code
                    progress.outcome = 'active_child_uncertain' if code is None else 'failed_or_unqualified'
                    progress.raw_receipts = raw_receipts(config.host_root/progress.step.run_id)
            except BaseException as observation_error:  # noqa: BLE001 - original and observation failures are both durable.
                receipt.error += '; child observation: '+repr(observation_error)
        save(receipt_path if config.output.is_dir() else owner_path, receipt)
        return 1
    finally:
        for restored_signal, handler in previous.items():
            signal.signal(restored_signal, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--dataset', choices=DATASETS)
    parser.add_argument('--write-plan', type=Path)
    args = parser.parse_args()
    try:
        if args.write_plan is not None:
            require(args.config is None and args.dataset is None, '--write-plan is exclusive')
            with args.write_plan.open('x') as stream:
                stream.write(build_plan().model_dump_json(indent=2)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
            directory_fsync(args.write_plan.parent)
            return 0
        require(args.config is not None and args.dataset is not None, '--config and --dataset required')
        return run(args.config, cast(Dataset, args.dataset))
    except (OSError, ValueError) as error:
        print(json.dumps({'outcome': 'queue_refusal_or_persistence_error', 'error': repr(error), 'observed_utc': utc()}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
