"""Exact portable documentation metadata gate contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
REPO = Path("/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/grust-report")
REPORT = Path("docs/reviews/sem-completion-2026-10-03")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Pin(Identity):
    path: Path


class Claim(Record):
    name: str
    evidence: Pin
    expected_fields: dict[str, JsonValue] = Field(min_length=1)
    scope: str


def safe(name: str) -> bool:
    p = Path(name)
    return (
        bool(name)
        and not p.is_absolute()
        and ".." not in p.parts
        and not any(c in name for c in "\n\r\x00\\")
    )


class Plan(Record):
    mode: Literal["candidate", "committed"]
    repo: Literal[
        "/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/grust-report"
    ]
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    changed_files: dict[str, Identity | None] = Field(min_length=1)
    helpers: dict[str, Identity]
    manifests: list[Pin] = Field(min_length=1)
    archives: list[Pin] = Field(min_length=1)
    primary_markdown: list[str] = Field(min_length=1)
    observed_claims: list[Claim] = Field(min_length=1)
    output: Path

    @model_validator(mode="after")
    def scope(self) -> Plan:
        if set(self.helpers) != {"doc_models.py", "doc_gate.py"}:
            raise ValueError("both frozen documentation helper identities required")
        if any(
            not safe(n) or not (n == "codex-to-codex.md" or n.startswith("docs/"))
            for n in self.changed_files
        ):
            raise ValueError(
                "gate scope contains only explicit safe docs/coordination changes"
            )
        if any(not safe(n) or not n.endswith(".md") for n in self.primary_markdown):
            raise ValueError("explicit primary Markdown paths required")
        for p in (
            *self.manifests,
            *self.archives,
            *(c.evidence for c in self.observed_claims),
        ):
            if (
                not p.path.is_absolute()
                or ".." in p.path.parts
                or not p.path.is_relative_to(REPO)
            ):
                raise ValueError(
                    "portable evidence pins must reside in the exact repository"
                )
        if any(
            p.path.suffix != ".json"
            for p in (*self.manifests, *(c.evidence for c in self.observed_claims))
        ):
            raise ValueError("observed claim/manifest pins must name metadata JSON")
        if (
            not self.output.is_absolute()
            or ".." in self.output.parts
            or self.output.parent != BASE
        ):
            raise ValueError("fresh verdict directory under completion root required")
        return self


class State(Record):
    head: str
    head_tree: str
    admitted_tree: str
    detached: bool
    status: str


class Check(Record):
    name: str
    passed: bool
    detail: str


class Receipt(Record):
    observed_utc: str
    outcome: Literal[
        "checking",
        "passed_candidate_documentation_metadata",
        "passed_committed_documentation_metadata",
        "error",
    ]
    mode: Literal["candidate", "committed"]
    repo: Path
    actual_commit: str
    admitted_tree: str
    detached: bool = False
    configuration: Pin
    helpers: list[Pin]
    source_before: State | None = None
    source_after: State | None = None
    checks: list[Check] = Field(default_factory=list)
    files: list[Pin] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    scope: str = "Portable documentation metadata identity and linked observed claims; not a new code/engine gate. Candidate qualifies the explicitly named base commit plus staged tree; final clean committed revision needs its own exact gate. Raw clocks remain archival shared-host observations."
