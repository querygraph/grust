"""Full, separate physical-output oracle for e0_cell.py.

This utility reads all original edges and all result rows after the owned
engine exits. It performs the explicit input validation absent from Pecan.
Fixed-budget paths are compared with bounded Bellman-Ford; a halted weighted
run is compared with independent heap Dijkstra, and halted landmark hops
with queue BFS. PageRank uses GraphX's delta recurrence on NumPy arrays.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.dataset as ds
from e0_cell import Arguments, Receipt
from numpy.typing import NDArray
from pydantic import TypeAdapter

MAX_HOPS = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class FilePin:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Graph:
    ids: NDArray[np.int64]
    source: NDArray[np.int64]
    target: NDArray[np.int64]
    weights: NDArray[np.float64]


@dataclass(slots=True)
class OracleReceipt:
    observed_utc: str
    status: str
    producer_receipt: FilePin
    before: list[FilePin]
    after: list[FilePin]
    program: str
    vertices: int = 0
    edges: int = 0
    result_rows: int = 0
    mismatch_rows: int = 0
    max_absolute_difference: float = 0.0
    error: str | None = None
    official_sssp: FilePin | None = None
    official_sssp_passed: bool = False


def pin(path: Path) -> FilePin:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return FilePin(str(path.resolve()), path.stat().st_size, digest.hexdigest())


def parquet_files(path: Path) -> list[Path]:
    paths = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
    if not paths:
        raise ValueError(f"no original Parquet files at {path}")
    return paths


def int64_column(table: pa.Table, name: str) -> NDArray[np.int64]:
    column = table[name]
    if column.type != pa.int64() or column.null_count:
        raise ValueError(f"{name} must be nonnull physical Int64")
    return np.asarray(column.combine_chunks().to_numpy(zero_copy_only=False), dtype=np.int64)


def positions(ids: NDArray[np.int64], values: NDArray[np.int64]) -> NDArray[np.int64]:
    found = np.searchsorted(ids, values)
    if np.any(found >= len(ids)) or np.any(ids[found] != values):
        raise ValueError("an endpoint or traversal source does not name a vertex")
    return found


def read_graph(arguments: Arguments) -> Graph:
    vertex_table = ds.dataset(str(arguments.vertices), format="parquet").to_table(columns=["id"])
    ids = np.sort(int64_column(vertex_table, "id"))
    if len(np.unique(ids)) != len(ids):
        raise ValueError("duplicate input vertex IDs")
    names = ["source", "target", *(["weight"] if arguments.input_weights else [])]
    edge_table = ds.dataset(str(arguments.edges), format="parquet").to_table(columns=names)
    source = positions(ids, int64_column(edge_table, "source"))
    target = positions(ids, int64_column(edge_table, "target"))
    weights = np.ones(len(source), dtype=np.float64)
    if arguments.input_weights:
        column = edge_table["weight"]
        if column.type != pa.float64() or column.null_count:
            raise ValueError("weight must be nonnull physical Float64")
        weights = np.asarray(column.combine_chunks().to_numpy(zero_copy_only=False), dtype=np.float64)
        if np.any(~np.isfinite(weights)) or np.any(weights < 0):
            raise ValueError("weights must be finite and nonnegative")
    if arguments.undirected:
        source, target = np.concatenate((source, target)), np.concatenate((target, source))
        weights = np.concatenate((weights, weights))
    return Graph(ids, source, target, weights)


def bounded_distances(
    graph: Graph, source: int, iterations: int, *, reverse: bool = False, weighted: bool = True
) -> NDArray[np.float64]:
    """Synchronous all-edge Bellman-Ford, independent of active-set Pregel."""
    start, end = (graph.target, graph.source) if reverse else (graph.source, graph.target)
    distance = np.full(len(graph.ids), np.inf, dtype=np.float64)
    distance[int(positions(graph.ids, np.array([source], dtype=np.int64))[0])] = 0.0
    weights = graph.weights if weighted else np.ones(len(start), dtype=np.float64)
    for _ in range(iterations):
        updated = distance.copy()
        np.minimum.at(updated, end, distance[start] + weights)
        distance = updated
    return distance


def adjacency(graph: Graph, reverse: bool) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]:
    start, end = (graph.target, graph.source) if reverse else (graph.source, graph.target)
    order = np.argsort(start, kind="stable")
    offsets = np.zeros(len(graph.ids) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(np.bincount(start, minlength=len(graph.ids)))
    return offsets, end[order], graph.weights[order]


def complete_distances(
    graph: Graph, source: int, *, reverse: bool = False, weighted: bool = True
) -> NDArray[np.float64]:
    offsets, targets, weights = adjacency(graph, reverse)
    root = int(positions(graph.ids, np.array([source], dtype=np.int64))[0])
    distance = np.full(len(graph.ids), np.inf, dtype=np.float64)
    distance[root] = 0.0
    if not weighted:
        queue = deque([root])
        while queue:
            vertex = queue.popleft()
            for target in targets[offsets[vertex] : offsets[vertex + 1]]:
                if np.isinf(distance[target]):
                    distance[target] = distance[vertex] + 1.0
                    queue.append(int(target))
        return distance
    pending = [(0.0, root)]
    while pending:
        cost, vertex = heapq.heappop(pending)
        if cost != distance[vertex]:
            continue
        for index in range(int(offsets[vertex]), int(offsets[vertex + 1])):
            target = int(targets[index])
            candidate = cost + float(weights[index])
            if candidate < distance[target]:
                distance[target] = candidate
                heapq.heappush(pending, (candidate, target))
    return distance


def pagerank(graph: Graph, arguments: Arguments, iterations: int) -> tuple[NDArray[np.float64], bool]:
    degree = np.bincount(graph.source, minlength=len(graph.ids))
    rank = np.full(len(graph.ids), arguments.reset, dtype=np.float64)
    delta = rank.copy()
    for step in range(iterations):
        active = np.ones(len(rank), dtype=np.bool_) if step == 0 else delta > arguments.tolerance
        contribution = np.where(active[graph.source], delta[graph.source] / degree[graph.source], 0.0)
        received = np.bincount(graph.target, weights=contribution, minlength=len(rank))
        delta = (1.0 - arguments.reset) * received
        rank += delta
    if arguments.normalized and rank.sum() != 0:
        rank /= rank.sum()
    return rank, bool(np.all(delta <= arguments.tolerance))


def compare(actual: NDArray[np.float64], expected: NDArray[np.float64], *, exact: bool) -> tuple[int, float]:
    finite = np.isfinite(expected) & np.isfinite(actual)
    matches = (actual == expected) if exact else np.isclose(actual, expected, rtol=1e-12, atol=1e-12)
    mismatches = int(np.count_nonzero(~matches))
    maximum = float(np.max(np.abs(actual[finite] - expected[finite]), initial=0.0))
    return mismatches, maximum


def qualify(producer: Receipt, graph: Graph, table: pa.Table, receipt: OracleReceipt) -> None:
    args = producer.arguments
    if producer.status != "completed_unvalidated" or not producer.session_stopped or producer.iterations is None:
        raise ValueError("producer did not complete and close its session")
    if not args.vote_to_halt and producer.iterations != args.iterations:
        raise ValueError("fixed-budget producer did not run its entire declared budget")
    if not args.vote_to_halt and producer.converged is not None:
        raise ValueError("fixed-budget producer must not claim a convergence result")
    if args.vote_to_halt and producer.converged is not True:
        raise ValueError("vote-to-halt producer did not converge")
    required = ["id", "pagerank"] if args.program == "pagerank" else ["id", "distance"]
    if args.program == "landmarks":
        required = ["id", *[f"dist_{key}" for key in sorted(args.landmarks)]]
    if table.column_names != required:
        raise ValueError("physical output columns differ from the declared program")
    output_ids = int64_column(table, "id")
    order = np.argsort(output_ids)
    if len(output_ids) != len(graph.ids) or not np.array_equal(output_ids[order], graph.ids):
        raise ValueError("physical output must contain every original vertex exactly once")
    receipt.vertices, receipt.edges, receipt.result_rows = len(graph.ids), len(graph.source), table.num_rows
    for name in required[1:]:
        column = table[name]
        if args.program == "landmarks":
            if column.type != pa.int32() or column.null_count:
                raise ValueError("landmark distances must be nonnull physical Int32")
            actual = np.asarray(column.combine_chunks().to_numpy(zero_copy_only=False), dtype=np.float64)[order]
            landmark = int(name.removeprefix("dist_"))
            expected = (
                complete_distances(graph, landmark, reverse=args.reversed_edges, weighted=False)
                if args.vote_to_halt
                else bounded_distances(
                    graph, landmark, producer.iterations, reverse=args.reversed_edges, weighted=False
                )
            )
            expected[np.isinf(expected)] = MAX_HOPS
            mismatches, maximum = compare(actual, expected, exact=True)
        else:
            if column.type != pa.float64():
                raise ValueError("distance/rank must have physical Float64 type")
            actual = np.asarray(column.combine_chunks().to_numpy(zero_copy_only=False), dtype=np.float64)[order]
            if args.program == "sssp":
                expected = (
                    complete_distances(graph, args.source)
                    if args.vote_to_halt
                    else bounded_distances(graph, args.source, producer.iterations)
                )
                if not np.array_equal(
                    np.asarray(column.is_null().to_numpy(zero_copy_only=False))[order], np.isinf(expected)
                ):
                    raise ValueError("only unreachable SSSP rows may be physically null")
                actual[np.isnan(actual)] = np.inf
            else:
                if column.null_count:
                    raise ValueError("PageRank must be nonnull")
                expected, converged = pagerank(graph, args, producer.iterations)
                if args.vote_to_halt and not converged:
                    raise ValueError("PageRank halt disagrees with the independent active-set recurrence")
            mismatches, maximum = compare(actual, expected, exact=False)
        receipt.mismatch_rows += mismatches
        receipt.max_absolute_difference = max(receipt.max_absolute_difference, maximum)
    if receipt.mismatch_rows:
        raise ValueError(f"{receipt.mismatch_rows} mismatched physical values")


def qualify_official_sssp(
    table: pa.Table, graph: Graph, arguments: Arguments, reference: Path, receipt: OracleReceipt
) -> None:
    """Compare every weighted SSSP value with an explicitly supplied Graphalytics reference."""
    if arguments.program != "sssp" or not arguments.vote_to_halt or not arguments.input_weights:
        raise ValueError("official SSSP comparison requires a completed weighted run to the halt")
    records = np.loadtxt(reference, dtype=[("id", np.int64), ("distance", np.float64)], ndmin=1)
    reference_ids = np.asarray(records["id"], dtype=np.int64)
    expected = np.asarray(records["distance"], dtype=np.float64)[np.argsort(reference_ids)]
    if len(reference_ids) != len(graph.ids) or not np.array_equal(np.sort(reference_ids), graph.ids):
        raise ValueError("official SSSP reference must cover the full original unique vertex domain")
    if np.any(np.isnan(expected)) or np.any(expected < 0):
        raise ValueError("official SSSP reference contains invalid distances")
    # Graphalytics uses the largest DOUBLE for unreachable; permit explicit +inf too.
    expected[expected == np.finfo(np.float64).max] = np.inf
    actual = np.asarray(table["distance"].combine_chunks().to_numpy(zero_copy_only=False), dtype=np.float64)
    actual = actual[np.argsort(int64_column(table, "id"))]
    actual[np.isnan(actual)] = np.inf
    mismatches, maximum = compare(actual, expected, exact=False)
    receipt.mismatch_rows += mismatches
    receipt.max_absolute_difference = max(receipt.max_absolute_difference, maximum)
    if mismatches:
        raise ValueError(f"{mismatches} mismatches against the full official SSSP reference")
    receipt.official_sssp_passed = True


def execute(cell: Path, output: Path, *, official_sssp: Path | None = None) -> None:
    producer_path = cell / "receipt.json"
    producer = TypeAdapter(Receipt).validate_json(producer_path.read_bytes())
    original_paths = [
        producer_path,
        *parquet_files(producer.arguments.vertices),
        *parquet_files(producer.arguments.edges),
        *parquet_files(cell / "result"),
    ]
    if official_sssp is not None:
        original_paths.append(official_sssp)
    receipt = OracleReceipt(
        datetime.now(timezone.utc).isoformat(),
        "running",
        pin(producer_path),
        [pin(path) for path in original_paths],
        [],
        producer.arguments.program,
    )
    try:
        graph = read_graph(producer.arguments)
        table = ds.dataset(str(cell / "result"), format="parquet").to_table()
        qualify(producer, graph, table, receipt)
        if official_sssp is not None:
            receipt.official_sssp = pin(official_sssp)
            qualify_official_sssp(table, graph, producer.arguments, official_sssp, receipt)
        receipt.after = [pin(path) for path in original_paths]
        if receipt.before != receipt.after:
            raise ValueError("an original input, producer receipt or raw output changed during qualification")
        receipt.status = "passed_full_physical_oracle"
    except BaseException as error:
        receipt.status = "error"
        receipt.error = f"{type(error).__name__}: {error}"
        raise
    finally:
        with output.open("x") as stream:
            stream.write(json.dumps(asdict(receipt), indent=2, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--official-sssp", type=Path)
    args = parser.parse_args()
    execute(args.cell, args.output, official_sssp=args.official_sssp)


if __name__ == "__main__":
    main()
