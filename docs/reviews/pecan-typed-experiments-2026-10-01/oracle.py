"""Independent physical cit-Patents WCC check; no Sail reads or normalization."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict


class Mismatch(RuntimeError):
    """The delivered physical result differs from the pinned full oracle."""


class FileIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    bytes: int
    sha256: str


class Correctness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    rows: int
    unique: int
    membership_mismatches: int = 0
    components: int
    largest_component_vertices: int
    canonicalization: str = "exact minimum original vertex ID"
    verification: str = "independent PyArrow full physical output versus pinned union-find membership"
    result_files: dict[str, FileIdentity]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_oracle(path: Path, expected_sha: str, rows: int, maximum: int) -> npt.NDArray[np.int64]:
    """Dataset-specific positive sparse IDs, not a general signed-ID conversion."""
    require(not path.is_symlink() and sha(path) == expected_sha and path.stat().st_size == rows * 16,
            "oracle hash/length mismatch")
    pairs: npt.NDArray[np.int64] = np.fromfile(path, dtype="<i8").reshape((-1, 2))
    ids, labels = pairs[:, 0], pairs[:, 1]
    require(len(ids) == rows and bool(np.all((ids > 0) & (ids <= maximum)))
            and bool(np.all(ids[1:] > ids[:-1])), "invalid oracle vertex domain/order")
    expected: npt.NDArray[np.int64] = np.full(maximum + 1, -1, dtype=np.int64)
    expected[ids] = labels
    require(bool(np.all((labels > 0) & (labels <= ids))), "invalid oracle representatives")
    require(bool(np.all(expected[labels] == labels)), "oracle representative is not a canonical member")
    require(sha(path) == expected_sha, "oracle changed during read")
    return expected


def inventory(directory: Path) -> dict[str, FileIdentity]:
    require(directory.is_dir() and not directory.is_symlink(), "missing/unsafe result directory")
    files: dict[str, FileIdentity] = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "result symlink")
        if path.is_file():
            files[str(path.relative_to(directory))] = FileIdentity(bytes=path.stat().st_size, sha256=sha(path))
        else:
            require(path.is_dir(), "special result file")
    return files


def verify_output(directory: Path, expected: npt.NDArray[np.int64], rows: int) -> Correctness:
    before = inventory(directory)
    files = [name for name in before if name.endswith(".parquet")]
    if not files:
        raise Mismatch("no result Parquet")
    seen: npt.NDArray[np.bool_] = np.zeros(len(expected), dtype=np.bool_)
    count = 0
    for name in files:
        with pq.ParquetFile(directory / name) as parquet:
            schema = parquet.schema_arrow
            if schema.names != ["id", "component"] or any(field.type != pa.int64() for field in schema):
                raise Mismatch("result must have exactly id:int64, component:int64")
            file_rows = 0
            for batch in parquet.iter_batches(batch_size=65536, use_threads=False):
                if any(column.null_count for column in batch.columns):
                    raise Mismatch("null vertex/component")
                ids, labels = [column.to_numpy(zero_copy_only=False) for column in batch.columns]
                if not bool(np.all((ids > 0) & (ids < len(expected)))):
                    raise Mismatch("out-of-range vertex")
                if bool(np.any(expected[ids] < 0)) or bool(np.any(seen[ids])) or len(np.unique(ids)) != len(ids):
                    raise Mismatch("unknown/duplicate vertex")
                if not bool(np.all(labels == expected[ids])):
                    raise Mismatch("exact minimum-ID component membership mismatch")
                seen[ids] = True
                file_rows += len(ids)
            if file_rows != parquet.metadata.num_rows:
                raise Mismatch("physical/footer row mismatch")
            count += file_rows
    if count != rows or int(np.count_nonzero(seen)) != rows or not bool(np.all(seen[expected >= 0])):
        raise Mismatch("incomplete vertex domain")
    require(inventory(directory) == before, "result bytes/inventory changed during verification")
    representatives, sizes = np.unique(expected[expected >= 0], return_counts=True)
    return Correctness(rows=count, unique=count, components=len(representatives),
                       largest_component_vertices=int(sizes.max()), result_files=before)
