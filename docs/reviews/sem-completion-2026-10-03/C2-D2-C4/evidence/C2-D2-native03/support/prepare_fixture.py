"""Prepare bounded immutable input/reference files, outside all engine timers."""
import argparse
import hashlib
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    bytes: int
    sha256: str


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    c2: list[list[int]]
    d2: list[list[int]]
    vertices: list[list[int]]
    edges: list[list[int]]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = 1
    vertex_rows: int = 4096
    edge_rows: int = 32768
    fragment_count: int = 8
    signed_high_bit_ids: bool = True
    nonmonotonic_file_order: bool = True
    files: dict[str, Identity]


def identity(path: Path) -> Identity:
    return Identity(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def signed_key(index: int) -> int:
    value = (index * 11400714819323198485 + 0x8000000000000000) & ((1 << 64) - 1)
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root: Path = args.output
    root.mkdir(parents=True, exist_ok=False)
    (root / "edges").mkdir()
    ids = [signed_key((i * 2053) % 4096) for i in range(4096)]
    vals = list(range(1, 4097))
    values_by_id = dict(zip(ids, vals, strict=True))
    pq.write_table(pa.table({"id": pa.array(ids, type=pa.int64()),
                             "val": pa.array(vals, type=pa.int64())}), root / "vertices.parquet")
    grouped: dict[int, list[int]] = {key: [] for key in ids}
    rounds: dict[int, list[int]] = {key: [] for key in ids}
    for fragment in range(8):
        sources = [ids[(i * 17 + fragment * 67) % 4096] for i in range(4096)]
        targets = [ids[(i * 29 + fragment * 31) % 4096] for i in range(4096)]
        payloads = [(fragment + 1) * 10000 + i for i in range(4096)]
        for source, target, value in zip(sources, targets, payloads, strict=True):
            grouped[source].append(value)
            rounds[target].append(values_by_id[source])
        pq.write_table(pa.table({"src": pa.array(sources, type=pa.int64()),
                                 "dst": pa.array(targets, type=pa.int64()),
                                 "payload": pa.array(payloads, type=pa.int64())}),
                       root / "edges" / f"part-{fragment:02}.parquet")
    references = Reference(
        c2=sorted([[key, min(values), len(values)] for key, values in grouped.items()]),
        d2=sorted([[key, sum(values), len(values)] for key, values in rounds.items()]),
        vertices=sorted([[key, value] for key, value in zip(ids, vals, strict=True)]),
        edges=sorted([[s, t, v] for part in range(8)
                          for s, t, v in zip(
                              [ids[(i * 17 + part * 67) % 4096] for i in range(4096)],
                              [ids[(i * 29 + part * 31) % 4096] for i in range(4096)],
                              [(part + 1) * 10000 + i for i in range(4096)], strict=True)]))
    (root / "reference.json").write_text(references.model_dump_json() + "\n")
    files = {p.relative_to(root).as_posix(): identity(p) for p in sorted(root.rglob("*")) if p.is_file()}
    manifest = Manifest(files=files)
    with (root / "manifest.json").open("x") as stream:
        stream.write(manifest.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


if __name__ == "__main__":
    main()
