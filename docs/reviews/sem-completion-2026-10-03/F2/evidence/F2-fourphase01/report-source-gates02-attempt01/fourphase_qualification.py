"""Read closed physical-oracle metadata; never open an input/output payload."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import f2a_models as models


class View(BaseModel):
    """Explicit acceptance-field subset; original JSON is retained separately."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class Identity(View):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Dataset(View):
    directory: Path
    files: dict[str, Identity]


class Output(Dataset):
    number: int


class OracleConfig(View):
    vertices: models.FilePin
    expected_rows: int
    reference: Dataset
    outputs: list[Output]
    output: Path
    metadata_pins: list[models.FilePin]


class PhysicalField(View):
    name: str
    arrow_type: str
    nullable: bool


class PhysicalSchema(View):
    name: str
    fields: list[PhysicalField]
    footer_rows: int
    scanned_rows: int


class Checked(View):
    number: int
    rows: int
    unique_rows: int
    components: int
    canonical_member_mismatches: int | None
    full_original_domain_passed: bool
    labels_in_original_domain: bool
    full_partition_equivalence_passed: bool
    physical_schemas: list[PhysicalSchema]


class Oracle(View):
    outcome: Literal["passed_full_physical_wcc"]
    started_utc: str
    finished_utc: str
    config: OracleConfig
    configuration: models.FilePin
    identities_before: dict[str, Identity]
    identities_after: dict[str, Identity]
    reference: Checked
    outputs: list[Checked]
    own_identity_closure_passed: Literal[True]
    full_output_oracle_passed: Literal[True]
    errors: list[str]


class Retained(models.Record):
    original: Path
    archive: Path
    bytes: int
    sha256: str


class Retention(models.Record):
    observed_utc: str
    outcome: Literal["all_eight_full_output_copies_match"]
    files: list[Retained]
    total_bytes: int
    originals_preserved: Literal[True]
    oracle_repeated: Literal[False]


def pin(path: Path) -> models.FilePin:
    if not path.is_file() or path.is_symlink():
        raise ValueError("regular closed metadata required")
    payload = path.read_bytes()
    if len(payload) >= 1_000_000:
        raise ValueError("small metadata only")
    return models.FilePin(
        path=path, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )


def qualified(
    path: Path, plan: models.Plan, required: list[models.FilePin]
) -> tuple[Oracle, models.FilePin]:
    receipt_pin = pin(path)
    oracle = Oracle.model_validate_json(path.read_bytes())
    if oracle.errors or oracle.identities_before != oracle.identities_after:
        raise ValueError("oracle errors/identity closure differ")
    if (
        pin(oracle.configuration.path) != oracle.configuration
        or oracle.config.output != path.parent
    ):
        raise ValueError("closed oracle/configuration namespace differs")
    if any(p not in oracle.config.metadata_pins or pin(p.path) != p for p in required):
        raise ValueError(
            "oracle does not bind the exact waited producer/worker/configuration"
        )
    if (
        oracle.config.vertices.path != plan.vertices
        or len(oracle.outputs) != plan.calls
    ):
        raise ValueError("oracle vertex binding/output count differs")
    count = oracle.config.expected_rows
    reference = oracle.reference
    if not (
        reference.number == 0
        and reference.rows == reference.unique_rows == count
        and reference.full_original_domain_passed
        and reference.labels_in_original_domain
        and reference.canonical_member_mismatches is None
        and not reference.full_partition_equivalence_passed
    ):
        raise ValueError("full reference domain or separate reference role differs")
    if len(oracle.config.outputs) != plan.calls:
        raise ValueError("oracle original output inventory differs")
    for number, (declared, checked) in enumerate(
        zip(oracle.config.outputs, oracle.outputs, strict=True), 1
    ):
        expected = plan.output / f"result-call{number}"
        if not (
            declared.number == checked.number == number
            and declared.directory == expected
            and checked.rows == checked.unique_rows == count
            and checked.full_original_domain_passed
            and checked.labels_in_original_domain
            and checked.full_partition_equivalence_passed
            and checked.canonical_member_mismatches == 0
        ):
            raise ValueError("full output domain/normalized partition proof differs")
        physical = {Path(s.name).name: s for s in checked.physical_schemas}
        if (
            set(physical) != set(declared.files)
            or sum(s.scanned_rows for s in physical.values()) != count
        ):
            raise ValueError("physical schema inventory/full scanned rows differ")
        for name, identity in declared.files.items():
            file = str(declared.directory / name)
            fields = {f.name: f.arrow_type for f in physical[name].fields}
            if (
                fields != {"id": "int64", "component": "int64"}
                or len(physical[name].fields) != 2
            ):
                raise ValueError("physical Int64 id/component schema differs")
            if oracle.identities_before.get(file) != identity:
                raise ValueError(
                    "physical output does not bind the closed full-file identity"
                )
    if pin(path) != receipt_pin:
        raise ValueError("oracle metadata changed while reading")
    return oracle, receipt_pin
