"""Seal an exact documentation metadata plan; never run its gate or mutate Git."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import doc_models as m
from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, model_validator

GATE = m.BASE / "report-metadata-gate02"
FREEZE_SHA = "d74b07ee0ff721116f0beaffa5d1b0d2d8fd06dda0634010b8e3afc968a116a0"
REPORT = m.REPO / m.REPORT
TOPICS = ("C2-D2-C4", "C3", "X2", "E0", "F2", "Vortex")
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

# Named object fields are read from retained evidence, including negative scope.
OBSERVED = {
    "C2-D2-C4/C2-summary.json": (
        "outcome",
        "fresh_producer_cells",
        "full_answer_actions",
        "full_server_phase_attribution",
        "physical_memory_accounting_qualified",
        "scope",
    ),
    "C2-D2-C4/D2-summary.json": (
        "outcome",
        "full_answer_actions",
        "facts.all180_rounds_strict_hash_2_1_0",
        "full_server_phase_attribution",
        "physical_memory_accounting_qualified",
        "scope",
    ),
    "C2-D2-C4/C4-summary.json": (
        "outcome",
        "full_answer_actions",
        "facts.allocation_factory_qualified",
        "facts.generic_struct_min_baseline_measured",
        "scope",
    ),
    "C3/portable-accounting.json": (
        "status",
        "host_source",
        "extension_source",
        "actual_lifecycle",
        "qualification",
    ),
    "X2/closed-controls.json": (
        "status",
        "full_reference_bfs",
        "historical_original_cause",
        "historical_original_zero_event_cases",
        "x1_two_host_qualification",
        "physical_memory_accounting_qualified",
        "native_os32_pss_accounting_qualified",
    ),
    "X2/historical-cases.json": (
        "status",
        "originals_rehashed",
        "logs_without_error_records",
        "logs_with_first_error_after_session_removal",
        "later_oom_not_a_cause_for_originals",
        "native_tiny_controls_not_large_replay",
        "x1_two_host_qualified",
    ),
    "E0/evidence/E0-gate03/receipt.json": (
        "outcome",
        "source_commit",
        "source_tree",
        "test_returncode",
        "forced_cleanup",
        "source_unchanged",
        "errors",
    ),
    "E0/evidence/E0-native01/review/closed-cells.json": (
        "status",
        "source_commit",
        "source_tree",
        "runtime_commit",
        "action_count_basis",
        "plans",
        "rss",
    ),
    "E0/evidence/E0-native-cit-active02/review/closed-cells.json": (
        "status",
        "source_commit",
        "source_tree",
        "runtime_commit",
        "action_count_basis",
        "plans",
        "rss",
    ),
    "F2/evidence/F2-fourphase-report02/receipt.json": (
        "outcome",
        "series",
        "completed_full_writes",
        "full_physical_qualification",
        "scope",
    ),
    "F2/evidence/F2-fourphase-main03/raw-archive-verification01.json": (
        "outcome",
        "total_bytes",
        "originals_preserved",
        "oracle_repeated",
    ),
    "Vortex/evidence/vortex-native_unregistered01/receipt.json": (
        "outcome",
        "attempts",
        "physical_checks",
        "server.wait_completed",
        "server.group_absent",
        "server.forced_cleanup",
        "errors",
        "scope",
    ),
    "Vortex/evidence/vortex-registered_reader01/receipt.json": (
        "outcome",
        "adapter_import_error",
        "server",
        "errors",
        "scope",
    ),
    "Vortex/evidence/vortex-registered_reader02/receipt.json": (
        "outcome",
        "attempts",
        "physical_checks",
        "server.wait_completed",
        "server.group_absent",
        "server.forced_cleanup",
        "errors",
        "scope",
    ),
}


class Config(m.Record):
    mode: Literal["candidate", "committed"]
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    root: Path
    output: Path
    primary_markdown: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def namespace(self) -> Config:
        for path in (self.root, self.output):
            if not path.is_absolute() or ".." in path.parts or path.parent != m.BASE:
                raise ValueError(
                    "fresh direct-child completion result directories required"
                )
        if self.root == self.output or not self.root.name.startswith("report-plan-"):
            raise ValueError("separate named plan and verdict namespaces required")
        return self


class Freeze(m.Record):
    model_config = ConfigDict(extra="ignore", strict=True)
    production_helpers: dict[str, m.Pin]


class Receipt(m.Record):
    observed_utc: str
    outcome: Literal["sealed_documentation_metadata_plan", "error"] = "error"
    configuration: m.Pin
    source: m.Pin
    gate_freeze: m.Pin
    plan: m.Pin | None = None
    files: int = 0
    manifests: int = 0
    archives: int = 0
    observed_claims: int = 0
    errors: list[str] = Field(default_factory=list)
    scope: str = "Exact documentation plan generation only; no gate, Git mutation, source/runtime/engine action, or full Sem completion claim. Observed values are copied from pinned retained JSON, including unsupported/unexplained/false qualification fields."


def pin(path: Path, maximum: int = 64 * 2**20) -> m.Pin:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise ValueError(f"unsafe or oversized metadata: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"metadata changed: {path}")
    return m.Pin(path=path, bytes=after.st_size, sha256=digest)


def read(expected: m.Pin) -> bytes:
    if expected.bytes > 16 * 2**20 or pin(expected.path) != expected:
        raise ValueError("bounded metadata identity differs")
    data = expected.path.read_bytes()
    if pin(expected.path) != expected:
        raise ValueError("metadata changed while decoding")
    return data


def field(value: JsonValue, name: str) -> JsonValue:
    for key in name.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"actual named evidence field missing: {name}")
        value = value[key]
    return value


def git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(m.REPO), *arguments], text=True, timeout=30
    )


def save(path: Path, record: m.Record) -> None:
    with path.open("x") as stream:
        stream.write(record.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(path: Path) -> int:
    configuration = pin(path, 16 * 2**20)
    config = Config.model_validate_json(read(configuration))
    config.root.mkdir(exist_ok=False)
    receipt = Receipt(
        observed_utc=datetime.now(UTC).isoformat(),
        configuration=configuration,
        source=pin(Path(__file__)),
        gate_freeze=pin(GATE / "freeze01.json"),
    )
    try:
        if receipt.gate_freeze.sha256 != FREEZE_SHA:
            raise ValueError(
                "requires exact strict documentation gate adapter02 freeze01"
            )
        freeze = Freeze.model_validate_json(read(receipt.gate_freeze))
        if set(freeze.production_helpers) != {"doc_models.py", "doc_gate.py"}:
            raise ValueError("exact two frozen documentation helpers required")
        for name, expected in freeze.production_helpers.items():
            if expected.path != GATE / name or pin(expected.path) != expected:
                raise ValueError("frozen helper origin/identity differs")
        if Path(m.__file__).resolve() != (GATE / "doc_models.py").resolve():
            raise ValueError("wrong imported documentation models")
        if config.output.exists() or git("rev-parse", "HEAD").strip() != config.commit:
            raise ValueError("fresh verdict namespace and exact current HEAD required")
        changed: dict[str, m.Identity | None] = {}
        for name in git(
            "diff", "--name-only", "-z", config.base_commit, config.tree
        ).split("\0"):
            if not name:
                continue
            if not m.safe(name) or not (
                name.startswith("docs/") or name == "codex-to-codex.md"
            ):
                raise ValueError("changed set exceeds documentation/coordination scope")
            actual = m.REPO / name
            changed[name] = (
                m.Identity(**pin(actual).model_dump(exclude={"path"}))
                if actual.exists()
                else None
            )
        manifests = [
            pin(REPORT / topic / "manifest.json", 16 * 2**20) for topic in TOPICS
        ]
        archives = [pin(p) for p in sorted(REPORT.rglob("*.tar.gz"))]
        if any(p.path.is_symlink() for p in archives):
            raise ValueError("archive symlink not admitted")
        claims: list[m.Claim] = []
        for relative, fields in OBSERVED.items():
            evidence = pin(REPORT / relative, 16 * 2**20)
            value = JSON.validate_json(read(evidence))
            claims.append(
                m.Claim(
                    name=relative,
                    evidence=evidence,
                    expected_fields={name: field(value, name) for name in fields},
                    scope="Pinned actual retained named fields only; original profile/resource/causal limits apply, not a new experiment or inferred completion.",
                )
            )
        primary = config.primary_markdown or [
            p.relative_to(m.REPO).as_posix()
            for p in sorted({REPORT / "README.md", *REPORT.glob("*/README.md")})
        ]
        plan = m.Plan(
            mode=config.mode,
            repo="/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/grust-report",
            commit=config.commit,
            base_commit=config.base_commit,
            tree=config.tree,
            changed_files=changed,
            helpers={
                name: m.Identity(bytes=p.bytes, sha256=p.sha256)
                for name, p in freeze.production_helpers.items()
            },
            manifests=manifests,
            archives=archives,
            primary_markdown=primary,
            observed_claims=claims,
            output=config.output,
        )
        identities = [
            receipt.configuration,
            receipt.source,
            receipt.gate_freeze,
            *freeze.production_helpers.values(),
            *manifests,
            *archives,
            *(claim.evidence for claim in claims),
        ]
        identities.extend(
            m.Pin(path=m.REPO / name, bytes=expected.bytes, sha256=expected.sha256)
            for name, expected in changed.items()
            if expected is not None
        )
        if (
            any(pin(p.path) != p for p in identities)
            or git("rev-parse", "HEAD").strip() != config.commit
        ):
            raise ValueError("plan/source/metadata identity closure differs")
        save(config.root / "plan.json", plan)
        receipt.plan = pin(config.root / "plan.json", 16 * 2**20)
        receipt.files, receipt.manifests, receipt.archives = (
            len(changed),
            len(manifests),
            len(archives),
        )
        receipt.observed_claims = len(claims)
        receipt.outcome = "sealed_documentation_metadata_plan"
    except Exception as error:  # noqa: BLE001 - failed sealing is retained and never launches a gate
        receipt.errors.append(repr(error))
    receipt.observed_utc = datetime.now(UTC).isoformat()
    save(config.root / "receipt.json", receipt)
    return 0 if receipt.outcome == "sealed_documentation_metadata_plan" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    raise SystemExit(execute(parser.parse_args().config))


if __name__ == "__main__":
    main()
