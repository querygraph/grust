"""Bounded inventories and physical Parquet batches outside the algorithm clock."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

import bfs_models as m
from bfs_certificate import I64, Bool


@dataclass(slots=True)
class Deadline:
    stop: float

    @classmethod
    def after(cls, seconds: int) -> Deadline:
        return cls(time.monotonic() + seconds)

    def check(self) -> None:
        if time.monotonic() >= self.stop:
            raise TimeoutError("outside-timer work/audit deadline elapsed")


def utc() -> str:
    return datetime.now(UTC).isoformat()


def pin(path: Path, deadline: Deadline) -> m.Pin:
    deadline.check()
    before = path.lstat()
    if not path.is_absolute() or not stat.S_ISREG(before.st_mode):
        raise ValueError("regular absolute immutable file required")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 2**20):
            deadline.check()
            digest.update(block)
    after = path.lstat()
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key) for key in keys):
        raise ValueError("file changed while hashing")
    return m.Pin(path=path, bytes=after.st_size, sha256=digest.hexdigest())


def read(expected: m.Pin, deadline: Deadline) -> bytes:
    if expected.bytes > 16 * 2**20 or pin(expected.path, deadline) != expected:
        raise ValueError("metadata pin/size differs")
    data = expected.path.read_bytes()
    if pin(expected.path, deadline) != expected:
        raise ValueError("metadata changed while decoding")
    return data


def snapshot(pins: list[m.Pin], deadline: Deadline) -> list[m.Pin]:
    unique: dict[Path, m.Pin] = {}
    for expected in pins:
        if expected.path in unique and unique[expected.path] != expected:
            raise ValueError("conflicting immutable pins")
        unique[expected.path] = expected
    actual = [pin(path, deadline) for path in sorted(unique)]
    if actual != [unique[path] for path in sorted(unique)]:
        raise ValueError("immutable source/input/client/helper pin differs")
    return actual


def inventory(result: m.ResultSet, deadline: Deadline) -> dict[str, m.Identity]:
    if not stat.S_ISDIR(result.directory.lstat().st_mode):
        raise ValueError("result must be a real directory")
    actual: dict[str, m.Identity] = {}
    for directory, children, names in os.walk(result.directory, followlinks=False):
        deadline.check()
        for name in children:
            if not stat.S_ISDIR((Path(directory) / name).lstat().st_mode):
                raise ValueError("raw result directory symlink/non-directory")
        for name in names:
            path = Path(directory) / name
            value = pin(path, deadline)
            actual[path.relative_to(result.directory).as_posix()] = m.Identity(
                bytes=value.bytes, sha256=value.sha256
            )
    if actual != result.files:
        raise ValueError("complete raw result inventory differs")
    return actual


def source(contract: m.SourceContract, deadline: Deadline) -> m.SourceObservation:
    def git(*args: str) -> str:
        deadline.check()
        return subprocess.check_output(
            ["git", "-C", str(contract.repo), *args],
            text=True,
            timeout=min(10, max(0.001, deadline.stop - time.monotonic())),
        ).strip()

    observed = m.SourceObservation(
        head=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        status=git("status", "--porcelain"),
        detached=not git("branch", "--show-current"),
    )
    if (
        observed.head != contract.head
        or observed.tree != contract.tree
        or observed.status
        or not observed.detached
    ):
        raise ValueError("exact detached source HEAD/tree/clean contract differs")
    return observed


def parquet(path: Path, names: tuple[str, ...]) -> pq.ParquetFile:
    file = pq.ParquetFile(path, memory_map=False, pre_buffer=False, buffer_size=0)
    schema = file.schema_arrow
    if tuple(schema.names) != names or any(
        not pa.types.is_int64(field.type) for field in schema
    ):
        raise ValueError(f"physical signed Int64 fields differ: {path.name}")
    return file


def edge_parquet(path: Path, config: m.Config) -> pq.ParquetFile:
    """Admit the complete physical input schema; BFS reads endpoints only."""
    file = pq.ParquetFile(path, memory_map=False, pre_buffer=False, buffer_size=0)
    schema = file.schema_arrow
    endpoints = (config.edge_source, config.edge_target)
    names = (
        (*endpoints, "weight")
        if config.edge_schema_profile == "original_weight3"
        else endpoints
    )
    if tuple(schema.names) != names:
        raise ValueError(
            "complete physical edge fields differ from the explicit profile"
        )
    if any(not pa.types.is_int64(schema.field(name).type) for name in endpoints):
        raise ValueError("physical edge endpoints must be signed Int64")
    if config.edge_schema_profile == "original_weight3" and not pa.types.is_float64(
        schema.field("weight").type
    ):
        raise ValueError("retained original weight field must be physical Float64")
    return file


def batches(
    file: pq.ParquetFile,
    rows: int,
    deadline: Deadline,
    columns: tuple[str, ...] | None = None,
) -> Iterator[pa.RecordBatch]:
    for batch in file.iter_batches(
        batch_size=rows,
        use_threads=False,
        columns=list(columns) if columns is not None else None,
    ):
        deadline.check()
        yield batch


def integers(batch: pa.RecordBatch, name: str, nullable: bool) -> tuple[I64, Bool]:
    column = batch.column(batch.schema.get_field_index(name))
    if not nullable and column.null_count:
        raise ValueError(f"required physical column {name} contains nulls")
    values = cast(
        I64,
        np.asarray(column.fill_null(0).to_numpy(zero_copy_only=False), dtype=np.int64),
    )
    valid = cast(
        Bool,
        np.asarray(column.is_valid().to_numpy(zero_copy_only=False), dtype=np.bool_),
    )
    return values, valid


def load_vertices(config: m.Config, receipt: m.Receipt, deadline: Deadline) -> I64:
    files = [parquet(expected.path, ("id",)) for expected in config.vertices]
    if sum(file.metadata.num_rows for file in files) != config.expected_vertices:
        raise ValueError("original vertex footer row count differs")
    ids = np.empty(config.expected_vertices, dtype=np.int64)
    rows = 0
    for file in files:
        for batch in batches(file, config.limits.batch_rows, deadline):
            values, _ = integers(batch, "id", False)
            if rows + len(values) > len(ids):
                raise ValueError("original vertices exceed declared domain")
            ids[rows : rows + len(values)] = values
            rows += len(values)
    if rows != len(ids):
        raise ValueError("original vertex physical rows differ")
    ids.sort(kind="quicksort")  # In-place O(log V) auxiliary sort workspace.
    deadline.check()
    for start in range(0, len(ids) - 1, config.limits.batch_rows):
        end = min(len(ids) - 1, start + config.limits.batch_rows)
        if np.any(ids[start:end] == ids[start + 1 : end + 1]):
            raise ValueError("original vertices are not unique")
    receipt.vertex_rows = rows
    return cast(I64, ids)


def save(path: Path, receipt: m.Receipt) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
