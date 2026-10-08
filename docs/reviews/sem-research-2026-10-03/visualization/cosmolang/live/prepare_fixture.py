"""Small semantic control: large signed IDs, parallel edges, isolate, crossing groups."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from provider import Catalog


def prepare(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    ids = [
        f"v/research/{value}"
        for value in (-9007199254740993, 9007199254740993, 5, 6, 7, 8)
    ]
    vertices = pa.table(
        {
            "id": ids,
            "group_id": ["a", "a", "b", "b", "c", "c"],
            "x": [0.0, 1.0, 4.0, 5.0, 8.0, 9.0],
            "y": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        }
    )
    edges = pa.table(
        {
            "src": [ids[0], ids[0], ids[1], ids[2], ids[3]],
            "dst": [ids[1], ids[1], ids[2], ids[3], ids[4]],
        }
    )
    pq.write_table(vertices, output / "vertices.parquet")
    pq.write_table(edges, output / "edges.parquet")
    catalog = Catalog(
        "research-graph",
        "fixture-1",
        "all-v1",
        "groups-v1",
        "xy-v1",
        len(ids),
        5,
        sum(p.stat().st_size for p in output.glob("*.parquet")),
    )
    (output / "catalog.json").write_text(json.dumps(asdict(catalog), indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)


if __name__ == "__main__":
    main()
