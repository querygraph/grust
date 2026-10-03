"""Prepare a valid signed-ID fixture; independently inspect full closed output."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from probe_models import FilePin, OracleReceipt, ReferenceRow


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def pin(path: Path) -> FilePin:
    return FilePin(str(path), path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def fixture(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    ids = list(range(4096))
    ids[10], ids[11], ids[-1] = 2**63 - 1, -5, -(2**63)
    edges = [(ids[(index - 1) // 2], ids[index]) for index in range(1, 4095)]
    edges.extend(((0, ids[1]), (ids[7], ids[7]), (ids[-1], ids[-1])))
    pq.write_table(pa.table({"id": pa.array(ids, type=pa.int64())}), path / "vertices.parquet")
    (path / "edges").mkdir()
    for partition in range(8):
        selected = edges[partition::8]
        pq.write_table(
            pa.table(
                {
                    "src": pa.array([s for s, _ in selected], type=pa.int64()),
                    "dst": pa.array([d for _, d in selected], type=pa.int64()),
                }
            ),
            path / "edges" / f"part-{partition:02}.parquet",
        )
    neighbors: dict[int, list[int]] = {vertex: [] for vertex in ids}
    for src, dst in edges:
        neighbors[src].append(dst)
        neighbors[dst].append(src)
    hops = {0: 0}
    queue = deque([0])
    while queue:
        src = queue.popleft()
        for dst in neighbors[src]:
            if dst not in hops:
                hops[dst] = hops[src] + 1
                queue.append(dst)
    rows = [
        ReferenceRow(
            vertex,
            float(hops[vertex]) if vertex in hops else None,
            hops.get(vertex),
            (0 if vertex == 0 else min(n for n in neighbors[vertex] if hops.get(n) == hops[vertex] - 1))
            if vertex in hops
            else None,
        )
        for vertex in sorted(ids)
    ]
    (path / "reference.json").write_text(json.dumps([asdict(row) for row in rows], indent=2) + "\n")
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "observed_utc": utc(),
                "source": 0,
                "directed": False,
                "vertices": len(ids),
                "edges": len(edges),
                "reachable": len(hops),
                "max_hops": max(hops.values()),
                "has_id_zero": True,
                "signed_min_is_isolated": True,
                "signed_max_is_reachable": True,
                "duplicates_and_loops_preserved": True,
                "files": [asdict(pin(p)) for p in sorted(path.rglob("*")) if p.is_file()],
            },
            indent=2,
        )
        + "\n"
    )


def oracle(fixture_path: Path, cell: Path, destination: Path) -> None:
    files = [
        fixture_path / "manifest.json",
        fixture_path / "reference.json",
        fixture_path / "vertices.parquet",
        *sorted((fixture_path / "edges").glob("*.parquet")),
        cell / "receipt.json",
        *sorted((cell / "result").glob("*.parquet")),
    ]
    receipt = OracleReceipt(utc(), before=[pin(p) for p in files])
    try:
        producer = json.loads((cell / "receipt.json").read_text())
        if (
            producer["status"] != "completed_unvalidated"
            or not producer["session_stopped"]
            or not producer["converged"]
        ):
            raise ValueError("producer is not completed/closed/converged")
        expected = [ReferenceRow(**row) for row in json.loads((fixture_path / "reference.json").read_text())]
        table = pq.read_table(cell / "result")
        types = {field.name: field.type for field in table.schema}
        if types != {"id": pa.int64(), "distance": pa.float64(), "hops": pa.int64(), "parent": pa.int64()}:
            raise ValueError("physical reference-BFS schema differs")
        actual = [ReferenceRow(**row) for row in table.to_pylist()]
        if any(type(row.id) is not int for row in actual) or len({row.id for row in actual}) != len(actual):
            raise ValueError("null, noninteger or duplicate physical IDs")
        actual.sort(key=lambda row: row.id)
        receipt.rows = len(actual)
        receipt.mismatches = sum(a != e for a, e in zip(actual, expected, strict=True))
        if receipt.mismatches:
            raise ValueError("distance/hops/rooted tight parent oracle differs")
        receipt.reachable = sum(row.distance is not None for row in actual)
        receipt.max_hops = max(row.hops for row in actual if row.hops is not None)
        receipt.after = [pin(p) for p in files]
        if receipt.before != receipt.after:
            raise ValueError("original or physical output bytes changed")
        receipt.status = "passed_full_physical_reference_BFS_oracle"
    except BaseException as error:
        receipt.error = f"{type(error).__name__}: {error}"
        receipt.status = "error"
        raise
    finally:
        destination.write_text(json.dumps(asdict(receipt), indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--cell", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        fixture(args.fixture)
    else:
        if args.cell is None or args.output is None:
            parser.error("oracle requires --cell and --output")
        oracle(args.fixture, args.cell, args.output)


if __name__ == "__main__":
    main()
