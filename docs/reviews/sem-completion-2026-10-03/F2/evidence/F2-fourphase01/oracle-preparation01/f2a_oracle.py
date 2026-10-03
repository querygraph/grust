"""Full physical WCC partition comparison, outside all engine clocks."""

import argparse
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
import pydantic as pyd

I64 = npt.NDArray[np.int64]


class Record(pyd.BaseModel):
    model_config = pyd.ConfigDict(extra="forbid")


class Identity(Record):
    bytes: int = pyd.Field(ge=0)
    sha256: str = pyd.Field(pattern=r"^[0-9a-f]{64}$")


class FilePin(Identity):
    path: Path


class ResultDataset(Record):
    directory: Path
    files: dict[str, Identity]


class Output(ResultDataset):
    number: int = pyd.Field(ge=1, le=3)


class Config(Record):
    vertices: FilePin
    expected_rows: int = pyd.Field(ge=1)
    reference: ResultDataset
    outputs: tuple[Output, ...]
    output: Path
    metadata_pins: tuple[FilePin, ...] = ()
    batch_rows: int = pyd.Field(default=262_144, ge=1, le=1_048_576)
    work_seconds: float = pyd.Field(default=3600.0, gt=0, allow_inf_nan=False)
    closure_seconds: float = pyd.Field(default=3600.0, gt=0, allow_inf_nan=False)
    memory_bytes: int = pyd.Field(default=24 * 1024**3, ge=1)

    @pyd.model_validator(mode="after")
    def paths_and_calls(self) -> "Config":
        require(len(self.outputs) in (1, 3), "one or three complete outputs required")
        require(
            tuple(o.number for o in self.outputs)
            == tuple(range(1, len(self.outputs) + 1)),
            "output numbering differs",
        )
        paths = [self.reference.directory, *(o.directory for o in self.outputs)]
        require(
            all(
                p.is_absolute()
                for p in [
                    *paths,
                    self.output,
                    self.vertices.path,
                    *(p.path for p in self.metadata_pins),
                ]
            ),
            "absolute paths required",
        )
        normalized = [p.resolve() for p in paths]
        require(len(set(normalized)) == len(normalized), "reference/output aliases")
        destination = self.output.resolve()
        for source in [
            *normalized,
            self.vertices.path.resolve(),
            *(p.path.resolve() for p in self.metadata_pins),
        ]:
            require(
                destination != source
                and destination not in source.parents
                and source not in destination.parents,
                "oracle output overlaps protected input/reference/output",
            )
        for data in [self.reference, *self.outputs]:
            require(bool(data.files), "empty raw inventory")
            for name in data.files:
                relative = PurePosixPath(name)
                require(
                    not relative.is_absolute()
                    and relative.as_posix() == name
                    and not any(part in (".", "..") for part in relative.parts)
                    and "\\" not in name,
                    "unsafe inventory member",
                )
        return self


class PhysicalField(Record):
    name: str
    arrow_type: str
    nullable: bool


class PhysicalFile(Record):
    name: str
    fields: tuple[PhysicalField, ...]
    footer_rows: int
    row_groups: int
    largest_row_group_uncompressed_bytes: int
    scanned_rows: int = 0


class CheckedOutput(Record):
    number: int
    rows: int = 0
    unique_rows: int = 0
    components: int = 0
    canonical_member_mismatches: int | None = None
    full_original_domain_passed: bool = False
    labels_in_original_domain: bool = False
    full_partition_equivalence_passed: bool = False
    physical_schemas: list[PhysicalFile] = pyd.Field(default_factory=list)


class Receipt(Record):
    outcome: Literal["checking", "passed_full_physical_wcc", "error"] = "checking"
    started_utc: str
    finished_utc: str | None = None
    config: Config
    configuration: FilePin
    identities_before: dict[str, Identity] = pyd.Field(default_factory=dict)
    identities_after: dict[str, Identity] = pyd.Field(default_factory=dict)
    original_vertices_schema: PhysicalFile | None = None
    reference: CheckedOutput = pyd.Field(
        default_factory=lambda: CheckedOutput(number=0)
    )
    outputs: list[CheckedOutput] = pyd.Field(default_factory=list)
    memory_admission: dict[str, int | str] = pyd.Field(default_factory=dict)
    work_seconds: float | None = None
    closure_seconds: float | None = None
    own_identity_closure_passed: bool = False
    full_output_oracle_passed: bool = False
    errors: list[str] = pyd.Field(default_factory=list)
    scope: str = (
        "Full partition comparison to the sealed caller-supplied GF reference; "
        "reference engine provenance and waited producer closure are separate root proofs. "
        "No official Graphalytics topology/ground-truth or performance verdict."
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Deadline:
    def __init__(self, seconds: float) -> None:
        self.end = time.monotonic() + seconds

    def check(self) -> None:
        if time.monotonic() >= self.end:
            raise TimeoutError("cooperative oracle phase deadline exceeded")


def identity(path: Path, deadline: Deadline) -> Identity:
    deadline.check()
    require(
        path.is_file() and not path.is_symlink(),
        "unsafe/nonregular protected file: " + str(path),
    )
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024**2):
            deadline.check()
            digest.update(block)
    after = path.stat()
    require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "file changed while hashing: " + str(path),
    )
    deadline.check()
    return Identity(bytes=after.st_size, sha256=digest.hexdigest())


def actual_files(data: ResultDataset) -> dict[str, Path]:
    require(
        data.directory.is_dir() and not data.directory.is_symlink(),
        "unsafe result directory",
    )
    files: dict[str, Path] = {}
    for path in sorted(data.directory.rglob("*")):
        require(not path.is_symlink(), "symlink in result directory")
        if path.is_dir():
            continue
        require(path.is_file(), "nonregular result member")
        files[path.relative_to(data.directory).as_posix()] = path
    require(bool(files), "empty physical result directory")
    return files


def observe(
    config: Config,
    configuration: FilePin,
    deadline: Deadline,
    record: dict[str, Identity],
) -> None:
    pins = [config.vertices, configuration, *config.metadata_pins]
    helper = Path(__file__).resolve()
    for item in pins:
        observed = identity(item.path, deadline)
        record[str(item.path)] = observed
        require(
            observed == Identity(bytes=item.bytes, sha256=item.sha256),
            "sealed file differs: " + str(item.path),
        )
    record[str(helper)] = identity(helper, deadline)
    for data in [config.reference, *config.outputs]:
        files = actual_files(data)
        for path in files.values():
            record[str(path)] = identity(path, deadline)
        require(set(files) == set(data.files), "raw inventory member set differs")
        require(
            all(
                record[str(files[name])] == expected
                for name, expected in data.files.items()
            ),
            "sealed raw inventory identity differs",
        )


def physical(path: Path, expected: tuple[str, ...], deadline: Deadline) -> PhysicalFile:
    deadline.check()
    with pq.ParquetFile(path) as parquet:
        schema = parquet.schema_arrow
        descriptor = PhysicalFile(
            name=str(path),
            fields=tuple(
                PhysicalField(name=f.name, arrow_type=str(f.type), nullable=f.nullable)
                for f in schema
            ),
            footer_rows=parquet.metadata.num_rows,
            row_groups=parquet.metadata.num_row_groups,
            largest_row_group_uncompressed_bytes=max(
                (
                    parquet.metadata.row_group(i).total_byte_size
                    for i in range(parquet.metadata.num_row_groups)
                ),
                default=0,
            ),
        )
    deadline.check()
    return descriptor


def check_fields(descriptor: PhysicalFile, expected: tuple[str, ...]) -> None:
    names = [field.name for field in descriptor.fields]
    require(
        len(names) == len(expected)
        and len(set(names)) == len(expected)
        and set(names) == set(expected),
        "exact physical field names differ: " + descriptor.name,
    )
    require(
        all(field.arrow_type == "int64" for field in descriptor.fields),
        "raw physical types must be Int64: " + descriptor.name,
    )


def admit(config: Config, schemas: list[PhysicalFile], receipt: Receipt) -> None:
    largest = max(s.largest_row_group_uncompressed_bytes for s in schemas)
    modeled = 128 * config.expected_rows + 128 * config.batch_rows + largest
    receipt.memory_admission = {
        "ordinal_array_budget_bytes": 128 * config.expected_rows,
        "bounded_batch_budget_bytes": 128 * config.batch_rows,
        "largest_actual_row_group_bytes": largest,
        "modeled_managed_bytes": modeled,
        "declared_budget_bytes": config.memory_bytes,
        "scope": "Conservative O(V) array/workspace admission model, not measured RSS/OS peak or cap.",
    }
    require(
        modeled <= config.memory_bytes,
        "modeled oracle memory exceeds declared admission",
    )


def column(batch: pa.RecordBatch, name: str) -> I64:
    array = batch.column(batch.schema.get_field_index(name))
    require(
        array.null_count == 0 and array.type == pa.int64(),
        "null/wrong physical column: " + name,
    )
    return cast(I64, array.to_numpy(zero_copy_only=False))


def original_domain(config: Config, receipt: Receipt, deadline: Deadline) -> I64:
    descriptor = physical(config.vertices.path, ("id",), deadline)
    receipt.original_vertices_schema = descriptor
    check_fields(descriptor, ("id",))
    require(
        descriptor.footer_rows == config.expected_rows,
        "original vertex footer count differs",
    )
    ids = np.empty(config.expected_rows, dtype=np.int64)
    count = 0
    with pq.ParquetFile(config.vertices.path) as parquet:
        for batch in parquet.iter_batches(batch_size=config.batch_rows, columns=["id"]):
            deadline.check()
            values = column(batch, "id")
            end = count + len(values)
            require(end <= len(ids), "excess original vertices")
            ids[count:end] = values
            count = end
    require(count == len(ids), "missing original vertices")
    descriptor.scanned_rows = count
    ids.sort(kind="quicksort")
    require(bool(np.all(ids[1:] > ids[:-1])), "duplicate original vertex ID")
    deadline.check()
    return ids


def positions(ids: I64, keys: I64) -> npt.NDArray[np.intp]:
    ordinal = np.searchsorted(ids, keys)
    require(bool(np.all(ordinal < len(ids))), "ID outside original domain")
    require(bool(np.all(ids[ordinal] == keys)), "ID outside original domain")
    return ordinal


def partition(
    config: Config,
    data: ResultDataset,
    ids: I64,
    checked: CheckedOutput,
    deadline: Deadline,
) -> I64:
    names = sorted(name for name in data.files if name.endswith(".parquet"))
    require(bool(names), "no Parquet result files")
    checked.physical_schemas = [
        physical(data.directory / name, ("id", "component"), deadline) for name in names
    ]
    for descriptor in checked.physical_schemas:
        check_fields(descriptor, ("id", "component"))
    require(
        sum(s.footer_rows for s in checked.physical_schemas) == len(ids),
        "full result footer count differs",
    )
    labels = np.empty(len(ids), dtype=np.int64)
    seen = np.zeros(len(ids), dtype=np.bool_)
    for descriptor in checked.physical_schemas:
        with pq.ParquetFile(descriptor.name) as parquet:
            for batch in parquet.iter_batches(
                batch_size=config.batch_rows, columns=["id", "component"]
            ):
                deadline.check()
                keys, values = column(batch, "id"), column(batch, "component")
                ordinal = positions(ids, keys)
                require(
                    np.unique(ordinal).size == len(ordinal)
                    and not bool(np.any(seen[ordinal])),
                    "duplicate output IDs within/across batches/files",
                )
                positions(ids, values)
                labels[ordinal] = values
                seen[ordinal] = True
                descriptor.scanned_rows += len(keys)
                checked.rows += len(keys)
        require(
            descriptor.scanned_rows == descriptor.footer_rows,
            "file scan/footer count differs: " + descriptor.name,
        )
    checked.unique_rows = int(np.count_nonzero(seen))
    require(
        checked.rows == len(ids) and checked.unique_rows == len(ids),
        "incomplete original domain coverage",
    )
    checked.full_original_domain_passed = checked.labels_in_original_domain = True
    # One ordinal slot per declared original vertex, regardless of signed ID magnitude.
    group_ordinal = positions(ids, labels)
    minimum = np.full(len(ids), np.iinfo(np.int64).max, dtype=np.int64)
    np.minimum.at(minimum, group_ordinal, ids)
    canonical = minimum[group_ordinal]
    checked.components = int(np.count_nonzero(canonical == ids))
    deadline.check()
    return canonical


def save(config: Config, receipt: Receipt) -> None:
    target = config.output / "receipt.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n")
    temporary.replace(target)


def run(config: Config, configuration: FilePin) -> Receipt:
    config.output.mkdir(parents=True, exist_ok=False)
    receipt = Receipt(
        started_utc=utc(),
        config=config,
        configuration=configuration,
        outputs=[CheckedOutput(number=o.number) for o in config.outputs],
    )
    save(config, receipt)
    start = time.monotonic()
    work = Deadline(config.work_seconds)
    try:
        observe(config, configuration, work, receipt.identities_before)
        receipt.original_vertices_schema = physical(config.vertices.path, ("id",), work)
        schemas = [receipt.original_vertices_schema]
        for data, checked in zip(
            [config.reference, *config.outputs],
            [receipt.reference, *receipt.outputs],
            strict=True,
        ):
            checked.physical_schemas = [
                physical(data.directory / name, ("id", "component"), work)
                for name in sorted(data.files)
                if name.endswith(".parquet")
            ]
            require(bool(checked.physical_schemas), "no Parquet result files")
            schemas.extend(checked.physical_schemas)
        check_fields(receipt.original_vertices_schema, ("id",))
        for descriptor in schemas[1:]:
            check_fields(descriptor, ("id", "component"))
        admit(config, schemas, receipt)
        ids = original_domain(config, receipt, work)
        reference = partition(config, config.reference, ids, receipt.reference, work)
        for output, checked in zip(config.outputs, receipt.outputs, strict=True):
            candidate = partition(config, output, ids, checked, work)
            checked.canonical_member_mismatches = int(
                np.count_nonzero(candidate != reference)
            )
            checked.full_partition_equivalence_passed = (
                checked.canonical_member_mismatches == 0
            )
            if not checked.full_partition_equivalence_passed:
                receipt.errors.append(
                    f"call {output.number}: full canonical partition mismatch ({checked.canonical_member_mismatches} members)"
                )
        work.check()
    except Exception as error:  # noqa: BLE001 — durable evidence boundary for any checker failure.
        receipt.errors.append(type(error).__name__ + ": " + str(error))
    finally:
        receipt.work_seconds = time.monotonic() - start
        save(config, receipt)
        closure_start = time.monotonic()
        try:
            observe(
                config,
                configuration,
                Deadline(config.closure_seconds),
                receipt.identities_after,
            )
            require(
                receipt.identities_before == receipt.identities_after,
                "before/after identities differ",
            )
            receipt.own_identity_closure_passed = True
        except Exception as error:  # noqa: BLE001 — preserve closure failure instead of a false pass.
            receipt.errors.append("closure " + type(error).__name__ + ": " + str(error))
        receipt.closure_seconds = time.monotonic() - closure_start
        receipt.full_output_oracle_passed = (
            not receipt.errors
            and receipt.own_identity_closure_passed
            and all(
                o.full_original_domain_passed
                and o.labels_in_original_domain
                and o.full_partition_equivalence_passed
                for o in receipt.outputs
            )
        )
        receipt.outcome = (
            "passed_full_physical_wcc" if receipt.full_output_oracle_passed else "error"
        )
        receipt.finished_utc = utc()
        save(config, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args()
    source = options.config.resolve()
    observed = identity(source, Deadline(60))
    config = Config.model_validate_json(source.read_bytes())
    result = run(config, FilePin(path=source, **observed.model_dump()))
    print(result.outcome + " " + str(config.output / "receipt.json"))
    raise SystemExit(0 if result.outcome == "passed_full_physical_wcc" else 1)


if __name__ == "__main__":
    main()
