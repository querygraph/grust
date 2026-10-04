"""Offline physical result checks; run after the algorithm process exits.

WCC uses the pinned independent union-find pairs, as the earlier closed oracle
does. BFS uses separate portable little-endian int64 ID and distance arrays;
distance -1 denotes unreachable. This campaign's sparse positive-ID domain is
explicit. Neither loader is an input validation job inside an engine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict


class Mismatch(RuntimeError):
    """Delivered physical output violates the exact admitted result contract."""


class FileIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    bytes: int
    sha256: str


class PhysicalField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    name: str
    arrow_type: str
    nullable: bool


class PhysicalSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    file: str
    fields: list[PhysicalField]


class WccCorrectness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    rows: int
    unique: int
    membership_mismatches: int = 0
    components: int
    largest_component_vertices: int
    canonicalization: str = "exact minimum original vertex ID"
    verification: str = "independent full physical output versus pinned union-find membership"
    result_files: dict[str, FileIdentity]
    physical_schemas: list[PhysicalSchema]


class BfsCorrectness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    rows: int
    unique: int
    distance_mismatches: int = 0
    source: int
    directed: bool = True
    reachable_vertices: int
    unreachable_vertices: int
    maximum_finite_distance: int
    unreachable_adapter: str
    verification: str = "independent full physical output versus pinned directed BFS distances"
    result_files: dict[str, FileIdentity]
    physical_schemas: list[PhysicalSchema]


@dataclass(frozen=True, slots=True)
class WccReference:
    expected: npt.NDArray[np.int64]
    rows: int
    identity: FileIdentity


@dataclass(frozen=True, slots=True)
class BfsReference:
    ids: npt.NDArray[np.int64]
    distances: npt.NDArray[np.int64]
    source: int
    ids_identity: FileIdentity
    distances_identity: FileIdentity


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_array(path: Path, expected_sha: str, elements: int) -> npt.NDArray[np.int64]:
    require(not path.is_symlink() and path.is_file(), "missing/unsafe reference file")
    require(elements > 0 and path.stat().st_size == elements * 8,
            "reference length mismatch")
    require(sha(path) == expected_sha, "reference hash mismatch")
    array: npt.NDArray[np.int64] = np.fromfile(path, dtype="<i8")
    require(len(array) == elements and sha(path) == expected_sha,
            "reference changed during read")
    require(hashlib.sha256(memoryview(array).cast("B")).hexdigest() == expected_sha,
            "consumed reference bytes do not match pinned hash")
    return array


def load_wcc_reference(path: Path, expected_sha: str, rows: int,
                       maximum: int) -> WccReference:
    """Positive sparse-ID pairs, identical membership rules to the closed oracle."""
    require(0 < maximum <= np.iinfo(np.int64).max - 1, "invalid maximum ID")
    pairs = _read_array(path, expected_sha, rows * 2).reshape((-1, 2))
    ids, labels = pairs[:, 0], pairs[:, 1]
    require(bool(np.all((ids > 0) & (ids <= maximum)))
            and bool(np.all(ids[1:] > ids[:-1])), "invalid reference vertex domain/order")
    expected: npt.NDArray[np.int64] = np.full(maximum + 1, -1, dtype=np.int64)
    expected[ids] = labels
    require(bool(np.all((labels > 0) & (labels <= ids))), "invalid reference representatives")
    require(bool(np.all(expected[labels] == labels)),
            "reference representative is not a canonical member")
    expected.setflags(write=False)
    return WccReference(expected, rows, FileIdentity(bytes=rows * 16, sha256=expected_sha))


def load_bfs_reference(ids_path: Path, ids_sha: str, distances_path: Path,
                       distances_sha: str, rows: int, maximum: int,
                       source: int) -> BfsReference:
    """Dense by sorted vertex ordinal, not an allocation indexed by sparse IDs."""
    ids = _read_array(ids_path, ids_sha, rows)
    distances = _read_array(distances_path, distances_sha, rows)
    require(bool(np.all((ids > 0) & (ids <= maximum)))
            and bool(np.all(ids[1:] > ids[:-1])), "invalid reference vertex domain/order")
    require(-(2**63) <= source < 2**63, "source outside signed int64")
    source_position = int(np.searchsorted(ids, source))
    require(source_position < rows and int(ids[source_position]) == source,
            "reference source is not a vertex")
    # i32MAX is the external engine's unreachable sentinel, not a finite hop.
    require(bool(np.all((distances >= -1) & (distances < np.iinfo(np.int32).max))),
            "invalid reference BFS distance")
    require(int(distances[source_position]) == 0 and int(np.count_nonzero(distances == 0)) == 1,
            "reference source distance must be the only zero")
    ids.setflags(write=False)
    distances.setflags(write=False)
    return BfsReference(ids, distances, source,
                        FileIdentity(bytes=rows * 8, sha256=ids_sha),
                        FileIdentity(bytes=rows * 8, sha256=distances_sha))


def inventory(directory: Path) -> dict[str, FileIdentity]:
    require(directory.is_dir() and not directory.is_symlink(), "missing/unsafe result directory")
    files: dict[str, FileIdentity] = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "result symlink")
        if path.is_file():
            files[str(path.relative_to(directory))] = FileIdentity(
                bytes=path.stat().st_size, sha256=sha(path))
        else:
            require(path.is_dir(), "special result file")
    return files


def _parquets(files: dict[str, FileIdentity]) -> list[str]:
    names = [name for name in files if name.endswith(".parquet")]
    if not names:
        raise Mismatch("no result Parquet")
    return names


def _schema(name: str, schema: pa.Schema, fields: list[tuple[str, pa.DataType]], *,
            ordered: bool = True) -> PhysicalSchema:
    names = [field[0] for field in fields]
    valid_names = (schema.names == names if ordered else
                   len(schema.names) == len(names) and len(set(schema.names)) == len(names)
                   and set(schema.names) == set(names))
    if not valid_names or any(
        schema.field(field_name).type != expected_type
        for field_name, expected_type in fields
    ):
        raise Mismatch(f"unexpected physical schema for {name}: {schema}")
    return PhysicalSchema(file=name, fields=[PhysicalField(
        name=field.name, arrow_type=str(field.type), nullable=field.nullable) for field in schema])


def verify_wcc_output(directory: Path, reference: WccReference) -> WccCorrectness:
    before = inventory(directory)
    expected = reference.expected
    seen: npt.NDArray[np.bool_] = np.zeros(len(expected), dtype=np.bool_)
    count = 0
    schemas: list[PhysicalSchema] = []
    for name in _parquets(before):
        with pq.ParquetFile(directory / name) as parquet:
            schemas.append(_schema(name, parquet.schema_arrow,
                                   [("id", pa.int64()), ("component", pa.int64())]))
            file_rows = 0
            for batch in parquet.iter_batches(batch_size=65536, use_threads=False):
                if any(column.null_count for column in batch.columns):
                    raise Mismatch("null vertex/component")
                ids, labels = [column.to_numpy(zero_copy_only=False) for column in batch.columns]
                if not bool(np.all((ids > 0) & (ids < len(expected)))):
                    raise Mismatch("out-of-range vertex")
                if (bool(np.any(expected[ids] < 0)) or bool(np.any(seen[ids]))
                        or len(np.unique(ids)) != len(ids)):
                    raise Mismatch("unknown/duplicate vertex")
                if not bool(np.all(labels == expected[ids])):
                    raise Mismatch("exact minimum-ID component membership mismatch")
                seen[ids] = True
                file_rows += len(ids)
            if file_rows != parquet.metadata.num_rows:
                raise Mismatch("physical/footer row mismatch")
            count += file_rows
    if (count != reference.rows or int(np.count_nonzero(seen)) != reference.rows
            or not bool(np.all(seen[expected >= 0]))):
        raise Mismatch("incomplete vertex domain")
    require(inventory(directory) == before, "result bytes/inventory changed during verification")
    representatives, sizes = np.unique(expected[expected >= 0], return_counts=True)
    return WccCorrectness(rows=count, unique=count, components=len(representatives),
                          largest_component_vertices=int(sizes.max()), result_files=before,
                          physical_schemas=schemas)


def _bfs_distances(column: pa.Array[pa.Scalar[pa.DataType]],
                   engine: Literal["graphframes", "pecan"]) -> npt.NDArray[np.int64]:
    if engine == "graphframes":
        if column.null_count:
            raise Mismatch("null graphframes BFS distance")
        raw: npt.NDArray[np.int32] = column.to_numpy(zero_copy_only=False)
        distances = raw.astype(np.int64)
        distances[distances == np.iinfo(np.int32).max] = -1
        if bool(np.any(distances < -1)) or bool(np.any(raw < 0)):
            raise Mismatch("negative graphframes BFS distance")
        return distances
    # Null conversion happens solely here; NaN/inf remain invalid finite values.
    raw_float: npt.NDArray[np.float64] = column.to_numpy(zero_copy_only=False)
    nulls: npt.NDArray[np.bool_] = column.is_null().to_numpy(zero_copy_only=False)
    finite = raw_float[~nulls]
    if not bool(np.all(np.isfinite(finite) & (finite >= 0)
                       & (finite < np.iinfo(np.int32).max) & (finite == np.floor(finite)))):
        raise Mismatch("Pecan BFS distance is not a finite nonnegative integral hop")
    distances = np.full(len(raw_float), -1, dtype=np.int64)
    distances[~nulls] = finite.astype(np.int64)
    return distances


def verify_bfs_output(directory: Path, reference: BfsReference,
                      engine: Literal["graphframes", "pecan"]) -> BfsCorrectness:
    require(engine in ("graphframes", "pecan"), "unknown BFS physical adapter")
    before = inventory(directory)
    rows = len(reference.ids)
    seen: npt.NDArray[np.bool_] = np.zeros(rows, dtype=np.bool_)
    count = 0
    schemas: list[PhysicalSchema] = []
    distance_field = ((f"dist_{reference.source}", pa.int32()) if engine == "graphframes"
                      else ("distance", pa.float64()))
    for name in _parquets(before):
        with pq.ParquetFile(directory / name) as parquet:
            schemas.append(_schema(name, parquet.schema_arrow, [("id", pa.int64()), distance_field],
                                   ordered=False))
            file_rows = 0
            for batch in parquet.iter_batches(batch_size=65536, use_threads=False):
                id_column = batch.column(batch.schema.get_field_index("id"))
                distance_column = batch.column(batch.schema.get_field_index(distance_field[0]))
                if id_column.null_count:
                    raise Mismatch("null BFS vertex")
                ids = id_column.to_numpy(zero_copy_only=False)
                positions = np.searchsorted(reference.ids, ids)
                if bool(np.any(positions >= rows)):
                    raise Mismatch("unknown BFS vertex")
                if bool(np.any(reference.ids[positions] != ids)):
                    raise Mismatch("unknown BFS vertex")
                if bool(np.any(seen[positions])) or len(np.unique(ids)) != len(ids):
                    raise Mismatch("duplicate BFS vertex")
                distances = _bfs_distances(distance_column, engine)
                if not bool(np.all(distances == reference.distances[positions])):
                    raise Mismatch("exact directed BFS distance mismatch")
                seen[positions] = True
                file_rows += len(ids)
            if file_rows != parquet.metadata.num_rows:
                raise Mismatch("physical/footer row mismatch")
            count += file_rows
    if count != rows or not bool(np.all(seen)):
        raise Mismatch("incomplete BFS vertex domain")
    require(inventory(directory) == before, "result bytes/inventory changed during verification")
    reachable = reference.distances >= 0
    return BfsCorrectness(rows=count, unique=count, source=reference.source,
                          reachable_vertices=int(np.count_nonzero(reachable)),
                          unreachable_vertices=int(np.count_nonzero(~reachable)),
                          maximum_finite_distance=int(reference.distances[reachable].max()),
                          unreachable_adapter=("physical int32 2147483647 maps to reference -1"
                                               if engine == "graphframes" else
                                               "physical DOUBLE NULL maps to reference -1"),
                          result_files=before, physical_schemas=schemas)
