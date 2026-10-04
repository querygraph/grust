"""Portable B8 references and independent NumPy arithmetic; no engine imports."""
from __future__ import annotations

import hashlib
import mmap
import os
import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, model_validator

Shape = Literal['adjacency', 'representatives', 'min-label-initial-round']
I64 = npt.NDArray[np.int64]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
MASK = 2**64 - 1
PAIR_DTYPE = np.dtype([('first', '<i8'), ('second', '<i8')])
MEMORY_ENVELOPE: Literal[34359738368] = 34359738368
BATCH_ROWS: Literal[262144] = 262144
COLUMNS: dict[Shape, list[str]] = {'adjacency': ['src', 'dst'], 'representatives': ['id', 'representative'],
                                  'min-label-initial-round': ['id', 'component']}


class OwnedMapping(Protocol):
    """NumPy's owned mapping handle is absent from its public typing stubs."""

    _mmap: mmap.mmap | None


def shape_semantics() -> dict[Shape, str]:
    return {'adjacency': 'distinct original+reverse pairs; loops retained',
            'representatives': 'first-round non-self-loop endpoints only; min of signed f(id) and neighbor f(id); isolates omitted',
            'min-label-initial-round': 'every original vertex seeded with itself; minimum of own and undirected neighbor IDs; isolates retained'}


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0)
    sha256: Digest


class InputConfig(Record):
    vertices: Path
    edges: Path
    output: Path
    vertices_sha256: Digest
    edges_sha256: Digest

    @model_validator(mode='after')
    def paths(self) -> InputConfig:
        require(all(p.is_absolute() for p in (self.vertices, self.edges, self.output)), 'absolute paths required')
        require(self.output.resolve() not in (self.vertices.resolve(), self.edges.resolve()), 'separate reference output')
        return self


class InputIdentities(Record):
    vertices: Identity
    edges: Identity


class PhysicalField(Record):
    name: str
    arrow_type: str
    nullable: bool


class PhysicalSchema(Record):
    file: str
    fields: list[PhysicalField]


class Coefficients(Record):
    seed: Literal[42] = 42
    round: Literal[1] = 1
    a_signed_bigint: Literal[-4767286540954276203] = -4767286540954276203
    b_signed_bigint: Literal[2949826092126892291] = 2949826092126892291
    field_polynomial: str = 'x^64 + x^4 + x^3 + x + 1 (0x1b reduction)'
    minimum_order: Literal['signed BIGINT'] = 'signed BIGINT'


class ConstructionTimings(Record):
    populate_memmap_seconds: float = 0
    quicksort_seconds: float = 0
    dedup_write_seconds: float = 0
    hash_seconds: float = 0
    boundary: str = 'reference construction only; outside engine timer'


class Artifact(Record):
    file: str
    rows: int = Field(ge=0)
    columns: list[str]
    identity: Identity
    format: str = 'row-major pairs of little-endian signed int64; no header; 16 bytes/row'
    order: str = 'ascending signed lexicographic (first,second); unique first column for map shapes'
    construction: ConstructionTimings | None = None


class Admission(Record):
    vertex_rows: int
    edge_rows: int
    maximum_edge_row_group_rows: int
    estimated_memory_bytes: int
    estimated_reference_disk_bytes: int
    observed_free_bytes: int
    envelope_bytes: Literal[34359738368] = MEMORY_ENVELOPE
    batch_rows: Literal[262144] = BATCH_ROWS
    memory_model: str = '64E file-backed scratch+reference cache + 32R Arrow row-group allowance + 128V vertex/map arrays + 128B batch work + original-file bytes + 3GiB reserve'
    disk_model: str = '64E simultaneous adjacency scratch+sealed pairs + 32V two maps + 2GiB reserve; E,V,R from actual footers'


class ReferenceReceipt(Record):
    schema_version: Literal[1] = 1
    outcome: Literal['checking', 'passed', 'error'] = 'checking'
    started_utc: str
    finished_utc: str | None = None
    config: InputConfig
    boundary: str = 'explicit immutable-input/reference phase; outside all engine timers'
    controller_semantics: Literal['f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'] = 'f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a'
    helper_sha256: dict[str, str]
    packages: dict[str, str]
    inputs_before: InputIdentities | None = None
    inputs_after: InputIdentities | None = None
    input_schemas: list[PhysicalSchema] = Field(default_factory=list)
    vertex_rows: int | None = None
    edge_rows: int | None = None
    isolated_vertices: int | None = None
    admission: Admission | None = None
    coefficients: Coefficients = Field(default_factory=Coefficients)
    artifacts: dict[Shape, Artifact] = Field(default_factory=dict)
    phases_seconds: dict[str, float] = Field(default_factory=dict)
    semantics: dict[Shape, str] = Field(default_factory=shape_semantics)
    memory_scope: str = 'reference construction is sequential; no resident-graph or engine memory claim'
    error: str | None = None


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path: Path) -> Identity:
    require(path.is_file() and not path.is_symlink(), 'missing/nonregular/symlink file: ' + str(path))
    return Identity(bytes=path.stat().st_size, sha256=sha(path))


def save(path: Path, receipt: Record) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        stream.write(receipt.model_dump_json(indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def physical_schema(name: str, schema: pa.Schema) -> PhysicalSchema:
    return PhysicalSchema(file=name, fields=[PhysicalField(name=f.name, arrow_type=str(f.type), nullable=f.nullable) for f in schema])


def read_columns(path: Path, names: list[str]) -> tuple[list[I64], PhysicalSchema]:
    with pq.ParquetFile(path) as parquet:
        schema = parquet.schema_arrow
        require(all(name in schema.names and schema.field(name).type == pa.int64() for name in names), 'raw input BIGINT schema')
        table = parquet.read(columns=names, use_threads=False)
        require(table.num_rows == parquet.metadata.num_rows and all(c.null_count == 0 for c in table.columns), 'input footer/null values')
        columns: list[I64] = [c.combine_chunks().to_numpy(zero_copy_only=False) for c in table.columns]
        return columns, physical_schema(path.name, schema)


def admit(config: InputConfig) -> Admission:
    with pq.ParquetFile(config.vertices) as vertices, pq.ParquetFile(config.edges) as edges:
        vertex_rows, edge_rows = vertices.metadata.num_rows, edges.metadata.num_rows
        group_rows = max((edges.metadata.row_group(i).num_rows for i in range(edges.metadata.num_row_groups)), default=0)
    memory = 64 * edge_rows + 32 * group_rows + 128 * vertex_rows + 128 * BATCH_ROWS
    memory += config.vertices.stat().st_size + config.edges.stat().st_size + 3 * 2**30
    disk = 64 * edge_rows + 32 * vertex_rows + 2 * 2**30
    free = shutil.disk_usage(config.output).free
    require(memory <= MEMORY_ENVELOPE, 'reference memory model exceeds disclosed 32GiB envelope')
    require(free >= disk, 'reference disk admission')
    return Admission(vertex_rows=vertex_rows, edge_rows=edge_rows, maximum_edge_row_group_rows=group_rows,
                     estimated_memory_bytes=memory, estimated_reference_disk_bytes=disk, observed_free_bytes=free)


def edge_batches(path: Path) -> Iterator[tuple[I64, I64]]:
    with pq.ParquetFile(path) as parquet:
        schema = parquet.schema_arrow
        require(all(n in schema.names and schema.field(n).type == pa.int64() for n in ('source', 'target')), 'raw edge BIGINT schema')
        rows = 0
        for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=['source', 'target'], use_threads=False):
            require(all(c.null_count == 0 for c in batch.columns), 'NULL original endpoint')
            src: I64 = batch.column(0).to_numpy(zero_copy_only=False)
            dst: I64 = batch.column(1).to_numpy(zero_copy_only=False)
            rows += batch.num_rows
            yield src, dst
        require(rows == parquet.metadata.num_rows, 'input physical/footer row mismatch')


def edge_schema(path: Path) -> PhysicalSchema:
    with pq.ParquetFile(path) as parquet:
        return physical_schema(path.name, parquet.schema_arrow)


def input_identities(config: InputConfig) -> InputIdentities:
    actual = InputIdentities(vertices=identity(config.vertices), edges=identity(config.edges))
    require(actual.vertices.sha256 == config.vertices_sha256 and actual.edges.sha256 == config.edges_sha256, 'original input pins')
    return actual


def sorted_ids(vertices: I64) -> I64:
    require(vertices.ndim == 1 and vertices.dtype == np.dtype('int64'), 'signed64 vertex vector')
    result = np.sort(vertices)
    require(bool(np.all(result[1:] > result[:-1])), 'duplicate original vertex')
    return result


def signed(value: int) -> int:
    return value if value < 2**63 else value - 2**64


def splitmix_coefficients(seed: int = 42) -> tuple[int, int]:
    state = seed
    def next_word() -> int:
        nonlocal state
        state = (state + 0x9E3779B97F4A7C15) & MASK
        word = state
        word = ((word ^ (word >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & MASK
        return word ^ (word >> 31)
    a = next_word()
    while a == 0:
        a = next_word()
    return signed(a), signed(next_word())


def affine_signed(ids: I64, a: int, b: int) -> I64:
    """Independent carryless field multiply, applied to unsigned ID bit patterns."""
    bits = ids.view(np.uint64).copy()
    result = np.zeros(len(ids), dtype=np.uint64)
    factor = a & MASK
    for _ in range(64):
        addend = np.where((bits & np.uint64(1)) != 0, np.uint64(factor), np.uint64(0))
        np.bitwise_xor(result, addend, out=result)
        high = factor >> 63
        factor = ((factor << 1) & MASK) ^ (0x1B if high else 0)
        bits >>= np.uint64(1)
    np.bitwise_xor(result, np.uint64(b & MASK), out=result)
    return result.view(np.int64)


def write_adjacency_reference(directory: Path, edges: Path, edge_rows: int) -> Artifact:
    """Owned file-backed sort, then bounded dedup/write; no full E arrays/copy."""
    if not edge_rows:
        return write_pairs(directory, 'adjacency', np.empty((0, 2), dtype=np.int64))
    scratch = directory / 'adjacency-scratch.i64le'
    with scratch.open('xb') as stream:
        stream.truncate(edge_rows * 32)
    pairs = np.memmap(scratch, dtype='<i8', mode='r+', shape=(2 * edge_rows, 2))
    passed = False
    timings = ConstructionTimings()
    try:
        began = time.perf_counter()
        offset = 0
        for sources, targets in edge_batches(edges):
            stop = offset + len(sources)
            require(stop <= edge_rows, 'edge rows exceed admitted footer')
            pairs[offset:stop, 0], pairs[offset:stop, 1] = sources, targets
            pairs[edge_rows + offset:edge_rows + stop, 0], pairs[edge_rows + offset:edge_rows + stop, 1] = targets, sources
            offset = stop
        require(offset == edge_rows, 'edge rows below admitted footer')
        timings.populate_memmap_seconds = time.perf_counter() - began
        began = time.perf_counter()
        records = pairs.view(PAIR_DTYPE).reshape(-1)
        records.sort(order=('first', 'second'), kind='quicksort')
        del records
        timings.quicksort_seconds = time.perf_counter() - began
        began = time.perf_counter()
        path = directory / 'adjacency.i64le'
        rows = 0
        previous: tuple[int, int] | None = None
        with path.open('xb') as stream:
            for start in range(0, len(pairs), BATCH_ROWS):
                chunk = pairs[start:start + BATCH_ROWS]
                keep = np.ones(len(chunk), dtype=np.bool_)
                keep[1:] = np.any(chunk[1:] != chunk[:-1], axis=1)
                if previous is not None:
                    keep[0] = bool(chunk[0, 0] != previous[0] or chunk[0, 1] != previous[1])
                selected = chunk[keep]
                selected.tofile(stream)
                rows += len(selected)
                previous = int(chunk[-1, 0]), int(chunk[-1, 1])
            stream.flush()
            os.fsync(stream.fileno())
        pairs.flush()
        timings.dedup_write_seconds = time.perf_counter() - began
        began = time.perf_counter()
        artifact = Artifact(file=path.name, rows=rows, columns=COLUMNS['adjacency'], identity=identity(path), construction=timings)
        timings.hash_seconds = time.perf_counter() - began
        passed = True
    finally:
        # This owned scratch may be removed only after successful complete write.
        # Interrupted/failed scratch and partial output remain in the failed ID.
        mapping = cast(OwnedMapping, pairs)._mmap
        if not isinstance(mapping, mmap.mmap):
            raise TypeError('missing owned memmap handle')
        mapping.close()
        if passed:
            scratch.unlink()
    return artifact


@dataclass(slots=True)
class MapState:
    ids: I64
    hashed: I64
    representatives: I64
    minimum_ids: I64
    active: npt.NDArray[np.bool_]
    incident: npt.NDArray[np.bool_]


def map_state(ids: I64) -> MapState:
    a, b = splitmix_coefficients()
    require((a, b) == (-4767286540954276203, 2949826092126892291), 'actual f3b seed42 coefficients')
    hashed = affine_signed(ids, a, b)
    return MapState(ids, hashed, hashed.copy(), ids.copy(), np.zeros(len(ids), dtype=np.bool_), np.zeros(len(ids), dtype=np.bool_))


def accumulate(state: MapState, src: I64, dst: I64) -> None:
    left = np.searchsorted(state.ids, src)
    right = np.searchsorted(state.ids, dst)
    require(bool(np.all(left < len(state.ids))) and bool(np.all(right < len(state.ids))), 'endpoint outside vertex domain')
    require(bool(np.all(state.ids[left] == src)) and bool(np.all(state.ids[right] == dst)), 'missing original endpoint')
    state.incident[left], state.incident[right] = True, True
    np.minimum.at(state.minimum_ids, left, dst)
    np.minimum.at(state.minimum_ids, right, src)
    nonloop = src != dst
    left, right = left[nonloop], right[nonloop]
    state.active[left], state.active[right] = True, True
    np.minimum.at(state.representatives, left, state.hashed[right])
    np.minimum.at(state.representatives, right, state.hashed[left])


def finish_maps(state: MapState) -> tuple[I64, I64, int]:
    reps: I64 = np.column_stack((state.ids[state.active], state.representatives[state.active]))
    labels: I64 = np.column_stack((state.ids, state.minimum_ids))
    return reps, labels, int(len(state.ids) - np.count_nonzero(state.incident))


def initial_maps(ids: I64, sources: I64, targets: I64, *, batch_rows: int = 262144) -> tuple[I64, I64, int]:
    require(batch_rows > 0 and sources.shape == targets.shape, 'map batch/edge lengths')
    state = map_state(ids)
    for start in range(0, len(sources), batch_rows):
        src, dst = sources[start:start + batch_rows], targets[start:start + batch_rows]
        accumulate(state, src, dst)
    return finish_maps(state)


def stream_initial_maps(ids: I64, edges: Path) -> tuple[I64, I64, int]:
    state = map_state(ids)
    for src, dst in edge_batches(edges):
        accumulate(state, src, dst)
    return finish_maps(state)


def write_pairs(directory: Path, shape: Shape, pairs: I64) -> Artifact:
    require(pairs.ndim == 2 and pairs.shape[1] == 2 and pairs.dtype == np.dtype('int64'), 'reference pair schema')
    path = directory / (shape + '.i64le')
    with path.open('xb') as stream:
        pairs.astype('<i8', copy=False).tofile(stream)
        stream.flush()
        os.fsync(stream.fileno())
    return Artifact(file=path.name, rows=len(pairs), columns=COLUMNS[shape], identity=identity(path))


def read_receipt(path: Path, expected_sha256: str) -> ReferenceReceipt:
    require(sha(path) == expected_sha256, 'reference receipt pin')
    receipt = ReferenceReceipt.model_validate_json(path.read_text())
    require(sha(path) == expected_sha256 and receipt.outcome == 'passed', 'reference phase receipt')
    require(receipt.inputs_before is not None and receipt.inputs_before == receipt.inputs_after
            and set(receipt.artifacts) == set(COLUMNS), 'incomplete immutable references')
    return receipt


def load_pairs(receipt_path: Path, artifact: Artifact, shape: Shape) -> I64:
    require(artifact.columns == COLUMNS[shape] and artifact.file == shape + '.i64le', 'reference shape/schema binding')
    path = receipt_path.parent / artifact.file
    require(identity(path) == artifact.identity and artifact.identity.bytes == artifact.rows * 16, 'reference identity/length')
    pairs: I64 = (np.memmap(path, dtype='<i8', mode='r', shape=(artifact.rows, 2)) if artifact.rows
                  else np.empty((0, 2), dtype=np.int64))
    for start in range(1, len(pairs), BATCH_ROWS):
        stop = min(start + BATCH_ROWS, len(pairs))
        previous, current = pairs[start - 1:stop - 1], pairs[start:stop]
        if shape == 'adjacency':
            require(bool(np.all((current[:, 0] > previous[:, 0]) |
                                ((current[:, 0] == previous[:, 0]) & (current[:, 1] > previous[:, 1])))),
                    'reference pair ordering/uniqueness')
        else:
            require(bool(np.all(current[:, 0] > previous[:, 0])), 'reference unique map ID ordering')
    return pairs
