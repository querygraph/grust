"""One explicit input audit and independent BFS reference phase, outside timers.

Pinned cit-Patents Parquet bytes are only read. Direction, duplicates and
isolates are preserved. This helper neither launches nor imports either engine.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import resource
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from output_oracle import (
    FileIdentity,
    load_bfs_reference,
    load_wcc_reference,
    require,
    sha,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERTICES_SHA = "0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa"
EDGES_SHA = "70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f"
WCC_SHA = "b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc"
VERTEX_ROWS, EDGE_ROWS, MAXIMUM_ID = 3_774_768, 16_518_947, 6_009_554
LOGGER = logging.getLogger(__name__)


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class InputConfig(Record):
    inputs: Path
    output: Path
    source: int = Field(default=750000, strict=True, ge=-(2**63), le=2**63 - 1)

    @model_validator(mode="after")
    def paths(self) -> InputConfig:
        require(self.inputs.is_absolute() and self.output.is_absolute(),
                "configured paths must be absolute")
        require(not self.output.resolve().is_relative_to(self.inputs.resolve()),
                "output must be separate from borrowed input directory")
        return self


class OriginalInputs(Record):
    vertices: FileIdentity
    edges: FileIdentity
    wcc_membership: FileIdentity


class Artifact(Record):
    path: Path
    identity: FileIdentity
    format: str


class ReferenceArtifacts(Record):
    ids: Artifact
    bfs_distances: Artifact
    wcc_membership: Artifact


class Validation(Record):
    vertex_rows: int
    unique_vertices: int
    edge_rows: int
    minimum_id: int
    maximum_id: int
    isolated_vertex_count: int
    source: int
    endpoint_membership: str = "every directed edge source and target names a vertex"
    direction: str = "original source -> target"
    duplicate_edges: str = "preserved; neither counted nor removed"
    isolated_vertices: str = "preserved in full vertex domain"


class Certificate(Record):
    source: int
    reachable_vertices: int
    unreachable_vertices: int
    maximum_finite_distance: int
    all_edges_examined: int
    reachable_source_edges_examined: int
    predecessor_witness_vertices: int
    criterion: str = "source-only zero; all reachable-edge triangle bounds; reached predecessor witnesses"


class Timings(Record):
    initial_identity_seconds: float = 0
    parquet_load_seconds: float = 0
    schema_and_domain_seconds: float = 0
    csr_seconds: float = 0
    bfs_seconds: float = 0
    certificate_seconds: float = 0
    write_and_bind_seconds: float = 0
    final_identity_seconds: float = 0
    whole_phase_seconds: float = 0


class Memory(Record):
    process_maxrss_bytes: int
    process_maxrss_observation: str
    cgroup_memory_peak_bytes: int | None
    cgroup_memory_current_bytes: int | None


class Receipt(Record):
    started_utc: str
    finished_utc: str | None = None
    outcome: Literal["running", "passed", "error"] = "running"
    arguments: InputConfig
    boundary: str = "explicit input validation and independent reference phase; outside engine timers"
    helpers_sha256: dict[str, str]
    packages: dict[str, str]
    originals_before: OriginalInputs | None = None
    originals_after: OriginalInputs | None = None
    validation: Validation | None = None
    certificate: Certificate | None = None
    references: ReferenceArtifacts | None = None
    timings: Timings = Field(default_factory=Timings)
    memory: Memory | None = None
    adapters: list[str] = Field(default_factory=lambda: [
        "ids.i64le: ascending positive signed64 IDs, little-endian int64",
        "bfs-distances.i64le: same row ordinal as ids; little-endian int64; -1 unreachable",
        "graphframes physical int32 2147483647 -> reference -1 solely in output oracle",
        "Pecan physical DOUBLE NULL -> reference -1 solely in output oracle",
        "wcc-membership.i64le: original pinned sorted int64 little-endian (id,minimum-id) pairs",
    ])
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DirectedCsr:
    ids: npt.NDArray[np.int64]
    offsets: npt.NDArray[np.int64]
    targets: npt.NDArray[np.int64]


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(path: Path) -> FileIdentity:
    require(path.is_file() and not path.is_symlink(), f"missing/unsafe input: {path}")
    return FileIdentity(bytes=path.stat().st_size, sha256=sha(path))


def original_identities(inputs: Path) -> OriginalInputs:
    require(inputs.is_dir() and not inputs.is_symlink(), "missing/unsafe inputs directory")
    return OriginalInputs(vertices=identity(inputs / "cit-Patents-v.parquet"),
                          edges=identity(inputs / "cit-Patents-e.parquet"),
                          wcc_membership=identity(inputs / "wcc-membership.i64le"))


def check_pins(identities: OriginalInputs) -> None:
    require(identities.vertices.sha256 == VERTICES_SHA, "vertex input hash mismatch")
    require(identities.edges.sha256 == EDGES_SHA, "edge input hash mismatch")
    require(identities.wcc_membership.sha256 == WCC_SHA, "WCC reference hash mismatch")
    require(identities.wcc_membership.bytes == VERTEX_ROWS * 16, "WCC reference length mismatch")


def read_columns(path: Path, names: list[str]) -> tuple[npt.NDArray[np.int64], ...]:
    with pq.ParquetFile(path) as parquet:
        schema = parquet.schema_arrow
        require(schema.names == names and all(field.type == pa.int64() for field in schema),
                f"unexpected physical input schema: {path}: {schema}")
        table = parquet.read(use_threads=False)
        require(table.num_rows == parquet.metadata.num_rows, "input physical/footer row mismatch")
        require(all(column.null_count == 0 for column in table.columns), "null input value")
        return tuple(column.combine_chunks().to_numpy(zero_copy_only=False) for column in table.columns)


def sorted_vertices(vertices: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    require(vertices.ndim == 1 and vertices.dtype == np.dtype("int64") and len(vertices) > 0,
            "vertices must be a nonempty signed64 vector")
    ids = np.sort(vertices)
    require(bool(np.all(ids > 0)), "campaign expects positive vertex IDs")
    require(bool(np.all(ids[1:] > ids[:-1])), "duplicate vertex ID")
    return ids


def build_csr(ids: npt.NDArray[np.int64], sources: npt.NDArray[np.int64],
              targets: npt.NDArray[np.int64]) -> DirectedCsr:
    require(ids.ndim == 1 and len(ids) > 0 and bool(np.all(ids[1:] > ids[:-1])),
            "CSR requires sorted unique vertex IDs")
    require(sources.ndim == 1 and targets.ndim == 1 and len(sources) == len(targets)
            and sources.dtype == np.dtype("int64") and targets.dtype == np.dtype("int64"),
            "edges must be equal-length signed64 vectors")
    source_positions = np.searchsorted(ids, sources)
    target_positions = np.searchsorted(ids, targets)
    require(bool(np.all(source_positions < len(ids))) and bool(np.all(target_positions < len(ids))),
            "edge endpoint is not a vertex")
    require(bool(np.all(ids[source_positions] == sources))
            and bool(np.all(ids[target_positions] == targets)), "edge endpoint is not a vertex")
    order = np.argsort(source_positions, kind="stable")
    neighbours = target_positions[order].astype(np.int64, copy=False)
    counts = np.bincount(source_positions, minlength=len(ids))
    offsets: npt.NDArray[np.int64] = np.empty(len(ids) + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(counts, dtype=np.int64, out=offsets[1:])
    return DirectedCsr(ids, offsets, neighbours)


def source_position(csr: DirectedCsr, source: int) -> int:
    position = int(np.searchsorted(csr.ids, source))
    require(position < len(csr.ids) and int(csr.ids[position]) == source,
            "requested BFS source is not a vertex; source is not changed")
    return position


def isolated_vertex_count(csr: DirectedCsr) -> int:
    """Count vertices with neither an outgoing nor an incoming incident edge."""
    incident: npt.NDArray[np.bool_] = np.diff(csr.offsets) > 0
    incident[csr.targets] = True
    return int(np.count_nonzero(~incident))


def breadth_first_distances(csr: DirectedCsr, source: int) -> npt.NDArray[np.int64]:
    position = source_position(csr, source)
    distances: npt.NDArray[np.int64] = np.full(len(csr.ids), -1, dtype=np.int64)
    distances[position] = 0
    queue: deque[int] = deque([position])
    while queue:
        vertex = queue.popleft()
        next_distance = int(distances[vertex]) + 1
        for adjacent in csr.targets[int(csr.offsets[vertex]):int(csr.offsets[vertex + 1])]:
            neighbour = int(adjacent)
            if distances[neighbour] == -1:
                distances[neighbour] = next_distance
                queue.append(neighbour)
    return distances


def verify_bfs_certificate(csr: DirectedCsr, distances: npt.NDArray[np.int64],
                           source: int) -> Certificate:
    position = source_position(csr, source)
    require(distances.shape == csr.ids.shape and distances.dtype == np.dtype("int64")
            and bool(np.all((distances >= -1) & (distances < 2**31 - 1))),
            "invalid certified distance vector")
    require(int(distances[position]) == 0 and int(np.count_nonzero(distances == 0)) == 1,
            "source must be the only distance zero")
    require(len(csr.offsets) == len(csr.ids) + 1 and csr.offsets[0] == 0
            and csr.offsets[-1] == len(csr.targets)
            and bool(np.all(csr.offsets[1:] >= csr.offsets[:-1]))
            and bool(np.all((csr.targets >= 0) & (csr.targets < len(csr.ids)))),
            "invalid CSR topology")
    witness: npt.NDArray[np.bool_] = np.zeros(len(csr.ids), dtype=np.bool_)
    witness[position] = True
    reachable_edges = 0
    for start in range(0, len(csr.targets), 65536):
        stop = min(start + 65536, len(csr.targets))
        edge_sources = np.searchsorted(csr.offsets, np.arange(start, stop), side="right") - 1
        edge_targets = csr.targets[start:stop]
        before, after = distances[edge_sources], distances[edge_targets]
        active = before >= 0
        reachable_edges += int(np.count_nonzero(active))
        require(bool(np.all(~active | ((after >= 0) & (after <= before + 1)))),
                "reachable edge violates reachability or shortest-hop triangle bound")
        witness[edge_targets[active & (after == before + 1)]] = True
    reachable = distances >= 0
    require(bool(np.all(witness[reachable])), "reached vertex lacks a predecessor witness")
    return Certificate(source=source, reachable_vertices=int(np.count_nonzero(reachable)),
                       unreachable_vertices=int(np.count_nonzero(~reachable)),
                       maximum_finite_distance=int(distances[reachable].max()),
                       all_edges_examined=len(csr.targets),
                       reachable_source_edges_examined=reachable_edges,
                       predecessor_witness_vertices=int(np.count_nonzero(witness)) - 1)


def memory() -> Memory:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    byte_value = int(peak if sys.platform == "darwin" else peak * 1024)
    values: list[int | None] = []
    for name in ("memory.peak", "memory.current"):
        path = Path("/sys/fs/cgroup") / name
        values.append(int(path.read_text().strip()) if path.is_file() else None)
    return Memory(process_maxrss_bytes=byte_value,
                  process_maxrss_observation="getrusage self maximum RSS; macOS bytes, Linux KiB converted",
                  cgroup_memory_peak_bytes=values[0], cgroup_memory_current_bytes=values[1])


def save_receipt(path: Path, receipt: Receipt) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_array(path: Path, values: npt.NDArray[np.int64]) -> Artifact:
    with path.open("xb") as stream:
        values.astype("<i8", copy=False).tofile(stream)
        stream.flush()
        os.fsync(stream.fileno())
    return Artifact(path=path, identity=identity(path), format="little-endian signed64, one value per row")


def prepare(config: InputConfig) -> Receipt:
    # mkdir refuses every existing output generation, even an empty directory.
    config.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    receipt = Receipt(started_utc=utc(), arguments=config,
                      helpers_sha256={name: sha(Path(__file__).with_name(name))
                                      for name in ("prepare_inputs.py", "output_oracle.py")},
                      packages={"python": platform.python_version(), "numpy": np.__version__,
                                "pyarrow": pa.__version__})
    path = config.output / "receipt.json"
    save_receipt(path, receipt)
    timings = Timings()
    try:
        phase = time.perf_counter()
        before = original_identities(config.inputs)
        receipt = receipt.model_copy(update={"originals_before": before})
        check_pins(before)
        timings = timings.model_copy(update={"initial_identity_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        (vertices,) = read_columns(config.inputs / "cit-Patents-v.parquet", ["id"])
        sources, targets = read_columns(config.inputs / "cit-Patents-e.parquet", ["source", "target"])
        timings = timings.model_copy(update={"parquet_load_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        ids = sorted_vertices(vertices)
        require(len(ids) == VERTEX_ROWS and len(sources) == EDGE_ROWS
                and int(ids[-1]) == MAXIMUM_ID, "pinned graph dimensions mismatch")
        wcc = load_wcc_reference(config.inputs / "wcc-membership.i64le", WCC_SHA,
                                 VERTEX_ROWS, MAXIMUM_ID)
        require(bool(np.all(wcc.expected[ids] >= 0)), "WCC reference vertex domain mismatch")
        timings = timings.model_copy(update={"schema_and_domain_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        csr = build_csr(ids, sources, targets)
        source_position(csr, config.source)
        validation = Validation(vertex_rows=len(ids), unique_vertices=len(ids), edge_rows=len(sources),
                                minimum_id=int(ids[0]), maximum_id=int(ids[-1]), source=config.source,
                                isolated_vertex_count=isolated_vertex_count(csr))
        receipt = receipt.model_copy(update={"validation": validation})
        require(validation.isolated_vertex_count == 0,
                "pinned cit-Patents continuation requires zero isolated vertices")
        timings = timings.model_copy(update={"csr_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        distances = breadth_first_distances(csr, config.source)
        timings = timings.model_copy(update={"bfs_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        certificate = verify_bfs_certificate(csr, distances, config.source)
        receipt = receipt.model_copy(update={"certificate": certificate})
        timings = timings.model_copy(update={"certificate_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        id_artifact = write_array(config.output / "ids.i64le", ids)
        distance_artifact = write_array(config.output / "bfs-distances.i64le", distances)
        references = ReferenceArtifacts(ids=id_artifact, bfs_distances=distance_artifact,
            wcc_membership=Artifact(path=config.inputs / "wcc-membership.i64le",
                                    identity=before.wcc_membership,
                                    format="little-endian signed64 pairs (id,minimum-id)"))
        load_bfs_reference(id_artifact.path, id_artifact.identity.sha256, distance_artifact.path,
                           distance_artifact.identity.sha256, VERTEX_ROWS, MAXIMUM_ID, config.source)
        receipt = receipt.model_copy(update={"references": references})
        timings = timings.model_copy(update={"write_and_bind_seconds": time.perf_counter() - phase})
        phase = time.perf_counter()
        after = original_identities(config.inputs)
        receipt = receipt.model_copy(update={"originals_after": after})
        require(after == before, "original input bytes changed during explicit phase")
        require(id_artifact.identity == identity(id_artifact.path)
                and distance_artifact.identity == identity(distance_artifact.path),
                "emitted reference bytes changed during explicit phase")
        require(receipt.helpers_sha256 == {name: sha(Path(__file__).with_name(name))
                for name in receipt.helpers_sha256}, "phase helper bytes changed during run")
        timings = timings.model_copy(update={"final_identity_seconds": time.perf_counter() - phase})
        receipt = receipt.model_copy(update={"outcome": "passed"})
    except Exception:
        LOGGER.exception("Explicit input/reference phase failed")
        receipt = receipt.model_copy(update={"outcome": "error", "error": traceback.format_exc()})
    finally:
        if receipt.originals_before is not None and receipt.originals_after is None:
            phase = time.perf_counter()
            try:
                after = original_identities(config.inputs)
                receipt = receipt.model_copy(update={"originals_after": after})
                require(after == receipt.originals_before,
                        "original input bytes changed during failed explicit phase")
            except Exception:
                LOGGER.exception("Failed phase final input identity check also failed")
                receipt = receipt.model_copy(update={"outcome": "error",
                    "error": (receipt.error or "") + "\nFinal input identity check:\n" + traceback.format_exc()})
            timings = timings.model_copy(update={"final_identity_seconds": time.perf_counter() - phase})
        timings = timings.model_copy(update={"whole_phase_seconds": time.perf_counter() - started})
        receipt = receipt.model_copy(update={"finished_utc": utc(), "timings": timings, "memory": memory()})
        save_receipt(path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    config = InputConfig.model_validate_json(arguments.config.read_bytes())
    result = prepare(config)
    print(json.dumps({"outcome": result.outcome, "receipt": str(config.output / "receipt.json")}))
    return 0 if result.outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
