"""Full raw B8 Parquet oracle; execute only after the engine child exits."""
from __future__ import annotations

import argparse
import json
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import model_validator
from shape_reference import (
    COLUMNS,
    I64,
    MEMORY_ENVELOPE,
    PAIR_DTYPE,
    Artifact,
    Digest,
    Identity,
    PhysicalSchema,
    Record,
    ReferenceReceipt,
    Shape,
    identity,
    load_pairs,
    physical_schema,
    read_receipt,
    require,
    save,
)


class Mismatch(RuntimeError):
    """Delivered rows/schema/multiplicity differ from the sealed exact reference."""


@dataclass(frozen=True, slots=True)
class LoadedReference:
    shape: Shape
    receipt_path: Path
    receipt_identity: Identity
    receipt: ReferenceReceipt
    artifact: Artifact
    pairs: I64


class Progress(Record):
    file: str
    rows_examined: int
    physical_schemas: list[PhysicalSchema]


class OracleMemory(Record):
    seen_bitmap_bytes: int
    reference_mapped_bytes: int
    result_file_bytes: int
    maximum_result_row_group_rows: int
    batch_rows: Literal[65536] = 65536
    estimated_memory_bytes: int
    envelope_bytes: Literal[34359738368] = 34359738368
    model: str = 'reference mapped pages + result-file cache + 32R Arrow row-group allowance + 1 byte/reference row seen bitmap + 128B batch work + 2GiB reserve'


class Correctness(Record):
    outcome: Literal['passed'] = 'passed'
    shape: Shape
    rows: int
    unique: int
    expected_rows: int
    mismatches: Literal[0] = 0
    duplicate_rows: Literal[0] = 0
    full_oracle: Literal[True] = True
    comparison: str = 'every raw signed64 pair/ID/value, exact cardinality and uniqueness; no casts/normalization'
    reference_receipt: Identity
    reference_artifact: Artifact
    result_files: dict[str, Identity]
    result_files_after: dict[str, Identity]
    physical_schemas: list[PhysicalSchema]
    memory_admission: OracleMemory


class CheckConfig(Record):
    output: Path
    references: Path
    shape: Shape
    variant: Literal['union', 'array-explode']
    reference_receipt_sha256: Digest
    receipt_output: Path

    @model_validator(mode='after')
    def paths(self) -> CheckConfig:
        require(all(p.is_absolute() for p in (self.output, self.references, self.receipt_output)), 'absolute oracle paths')
        require(not self.receipt_output.resolve().is_relative_to(self.output.resolve())
                and not self.receipt_output.resolve().is_relative_to(self.references.resolve()), 'oracle receipt outside borrowed directories')
        return self


class CheckReceipt(Record):
    schema_version: Literal[1] = 1
    config: CheckConfig
    outcome: Literal['checking', 'passed', 'mismatch', 'error'] = 'checking'
    boundary: str = 'full physical output oracle, outside completed engine launch-through-exit timer'
    started_utc: str
    finished_utc: str | None = None
    oracle_seconds: float | None = None
    progress: Progress | None = None
    correctness: Correctness | None = None
    error: str | None = None
    traceback: str | None = None


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def check(value: bool, message: str) -> None:
    if not value:
        raise Mismatch(message)


def inventory(directory: Path) -> dict[str, Identity]:
    check(directory.is_dir() and not directory.is_symlink(), 'missing/unsafe result directory')
    files: dict[str, Identity] = {}
    for path in sorted(directory.rglob('*')):
        check(not path.is_symlink(), 'physical output symlink')
        if path.is_file():
            files[str(path.relative_to(directory))] = identity(path)
        else:
            check(path.is_dir(), 'physical output special file')
    return files


def load_shape_reference(references: Path, shape: Shape, expected_receipt_sha256: str) -> LoadedReference:
    path = references / 'receipt.json'
    receipt = read_receipt(path, expected_receipt_sha256)
    artifact = receipt.artifacts[shape]
    pairs = load_pairs(path, artifact, shape)
    return LoadedReference(shape, path, identity(path), receipt, artifact, pairs)


def verify_shape_output(output: Path, reference: LoadedReference, shape: Shape, *,
                        progress: Callable[[Progress], None] | None = None) -> Correctness:
    require(reference.shape == shape and reference.artifact.columns == COLUMNS[shape], 'oracle/reference shape binding')
    require(identity(reference.receipt_path) == reference.receipt_identity, 'reference receipt changed before oracle')
    before = inventory(output)
    names = [name for name in before if name.endswith('.parquet')]
    check(bool(names), 'no physical Parquet footer/schema')
    maximum_group = 0
    for name in names:
        with pq.ParquetFile(output / name) as parquet:
            maximum_group = max(maximum_group, max((parquet.metadata.row_group(i).num_rows
                               for i in range(parquet.metadata.num_row_groups)), default=0))
    file_bytes = sum(file.bytes for file in before.values())
    model_bytes = reference.artifact.identity.bytes + file_bytes + 32 * maximum_group
    model_bytes += reference.artifact.rows + 128 * 65536 + 2 * 2**30
    require(model_bytes <= MEMORY_ENVELOPE, 'outside-timer oracle memory model exceeds 32GiB envelope')
    memory = OracleMemory(seen_bitmap_bytes=reference.artifact.rows, reference_mapped_bytes=reference.artifact.identity.bytes,
                          result_file_bytes=file_bytes, maximum_result_row_group_rows=maximum_group, estimated_memory_bytes=model_bytes)
    expected = reference.pairs
    seen = np.zeros(reference.artifact.rows, dtype=np.bool_)
    total = 0
    schemas: list[PhysicalSchema] = []
    for name in names:
        file_rows = 0
        with pq.ParquetFile(output / name) as parquet:
            schema = parquet.schema_arrow
            schemas.append(physical_schema(name, schema))
            if progress is not None:
                progress(Progress(file=name, rows_examined=total, physical_schemas=schemas))
            check(schema.names == COLUMNS[shape] and all(f.type == pa.int64() for f in schema),
                  'wrong physical BIGINT names/order/types: ' + name)
            for batch in parquet.iter_batches(batch_size=65536, use_threads=False):
                check(all(c.null_count == 0 for c in batch.columns), 'NULL raw shape value: ' + name)
                values: I64 = np.ascontiguousarray(np.column_stack([c.to_numpy(zero_copy_only=False) for c in batch.columns]), dtype='<i8')
                if shape == 'adjacency':
                    positions = np.searchsorted(expected.view(PAIR_DTYPE).reshape(-1), values.view(PAIR_DTYPE).reshape(-1))
                else:
                    positions = np.searchsorted(expected[:, 0], values[:, 0])
                check(bool(np.all(positions < len(expected))), 'unexpected pair/vertex beyond reference: ' + name)
                check(bool(np.all(expected[positions] == values)), 'wrong raw pair/ID/value: ' + name)
                check(len(np.unique(positions)) == len(positions) and not bool(np.any(seen[positions])),
                      'duplicate raw pair/vertex: ' + name)
                seen[positions] = True
                total += batch.num_rows
                file_rows += batch.num_rows
            check(file_rows == parquet.metadata.num_rows, 'physical/footer rows differ: ' + name)
        if progress is not None:
            progress(Progress(file=name, rows_examined=total, physical_schemas=schemas))
    check(total == len(expected) and bool(np.all(seen)), 'missing raw output rows')
    after = inventory(output)
    require(before == after, 'physical output files changed during oracle')
    require(identity(reference.receipt_path) == reference.receipt_identity
            and identity(reference.receipt_path.parent / reference.artifact.file) == reference.artifact.identity,
            'sealed reference changed during oracle')
    return Correctness(shape=shape, rows=total, unique=total, expected_rows=len(expected),
                       reference_receipt=reference.receipt_identity, reference_artifact=reference.artifact,
                       result_files=before, result_files_after=after, physical_schemas=schemas, memory_admission=memory)


def run_check(config: CheckConfig) -> CheckReceipt:
    config.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    require(not config.receipt_output.exists(), 'refusing existing oracle receipt')
    receipt = CheckReceipt(config=config, started_utc=utc())
    save(config.receipt_output, receipt)
    start = time.perf_counter()
    def progress(value: Progress) -> None:
        receipt.progress = value
        save(config.receipt_output, receipt)
    try:
        reference = load_shape_reference(config.references, config.shape, config.reference_receipt_sha256)
        receipt.correctness = verify_shape_output(config.output, reference, config.shape, progress=progress)
        receipt.outcome = 'passed'
    except BaseException as error:  # noqa: BLE001 - retain mismatches, partial diagnostics, and interruptions
        receipt.outcome = 'mismatch' if isinstance(error, Mismatch) else 'error'
        receipt.error, receipt.traceback = repr(error), traceback.format_exc()
    finally:
        receipt.oracle_seconds = time.perf_counter() - start
        receipt.finished_utc = utc()
        save(config.receipt_output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    config = CheckConfig.model_validate_json(parser.parse_args().config.read_text())
    receipt = run_check(config)
    print(json.dumps({'outcome': receipt.outcome, 'receipt': str(config.receipt_output)}), flush=True)
    return 0 if receipt.outcome == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
