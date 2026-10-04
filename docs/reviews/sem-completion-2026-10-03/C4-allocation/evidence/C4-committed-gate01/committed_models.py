"""Commit-bound Rust gates with previously closed exact-byte allocator controls."""

from pathlib import Path
from typing import Literal

import allocator_models as native
from pydantic import Field, field_validator, model_validator

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
COMMIT: Literal["ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9"] = (
    "ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9"
)
TREE: Literal["268779f765b88813ec737beb1b30442eb30a5e72"] = (
    "268779f765b88813ec737beb1b30442eb30a5e72"
)
HELPERS = {"committed_models.py", "committed_owner.py", "wait_committed.py"}
REUSE_FREEZE_SHA = "9201418dd3ef543601f35fb89462a4c4c156c27588ceae4f01d686b1ebc55b27"
RUST_NAMES = ("rustc-version", "cargo-version", "fmt", "clippy", "test", "release")
PROBES = (
    (4096, "tuple-min"),
    (4096, "min-by"),
    (100000, "tuple-min"),
    (100000, "min-by"),
    (100000, "min-by"),
    (100000, "tuple-min"),
)
PROBE_NAMES = tuple(
    f"probe-{i:02}-{n}-{method}" for i, (n, method) in enumerate(PROBES, 1)
)


class Config(native.Record):
    root: Path
    repository: Path
    commit: Literal["ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9"] = COMMIT
    tree: Literal["268779f765b88813ec737beb1b30442eb30a5e72"] = TREE
    source_prefix: Literal["probe"] = "probe"
    candidate_configuration: native.Pin
    candidate_receipt: native.Pin
    candidate_launch: native.Pin
    candidate_binary: native.Pin
    reused_owner_freeze: native.Pin
    helpers: dict[str, native.Pin]
    total_seconds: int = Field(default=7200, ge=300, le=14400)
    step_seconds: int = Field(default=3600, ge=30, le=7200)
    fd_soft: Literal[8192] = 8192

    @model_validator(mode="after")
    def scope(self) -> "Config":
        if (
            self.root.parent != BASE
            or not self.root.name.startswith("C4-allocation-run")
            or not self.root.name.endswith("-committed")
        ):
            raise ValueError("fresh committed C4 result namespace required")
        if self.repository != Path(
            "/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/c4-allocation-source01"
        ):
            raise ValueError("exact committed standalone repository required")
        if set(self.helpers) != HELPERS or any(
            p.path.name != n for n, p in self.helpers.items()
        ):
            raise ValueError("exact new helper origins required")
        if self.reused_owner_freeze.sha256 != REUSE_FREEZE_SHA:
            raise ValueError("frozen source-only owner02 identity differs")
        if (
            self.candidate_receipt.path.parent != self.candidate_launch.path.parent
            or self.candidate_receipt.path.name != "receipt.json"
            or self.candidate_launch.path.name != "launch-receipt.json"
        ):
            raise ValueError("same actual candidate owner/launcher attempt required")
        if self.root == self.candidate_receipt.path.parent:
            raise ValueError("candidate runtime evidence cannot be overwritten")
        if self.step_seconds > self.total_seconds:
            raise ValueError("step budget exceeds campaign cap")
        return self


class StrictStep(native.Step):
    returncode: int | None = Field(default=None, strict=True)
    waited: bool = Field(default=False, strict=True)
    group_absent: bool = Field(default=False, strict=True)
    forced_cleanup: bool = Field(default=False, strict=True)


class Candidate(native.Receipt):
    immutable_source_tool_helper_closure: bool = Field(default=False, strict=True)
    all_owned_groups_absent: bool = Field(default=False, strict=True)
    locks_released: bool = Field(default=False, strict=True)

    @field_validator("steps", mode="before")
    @classmethod
    def strict_steps(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("actual step list required")  # noqa: TRY004 - Pydantic validation error
        return [StrictStep.model_validate(row) for row in value]


class CandidateWait(native.Launch):
    returncode: int | None = Field(default=None, strict=True)
    waited: bool = Field(default=False, strict=True)
    owner_group_absent: bool = Field(default=False, strict=True)
    forced_cleanup: bool = Field(default=False, strict=True)


class GitProof(native.Record):
    head: str
    tree: str
    detached: bool = Field(strict=True)
    status: str
    tracked: list[str]


class Limits(native.Record):
    soft: int
    hard: int


class Receipt(native.Record):
    outcome: Literal[
        "running", "passed_committed_native_rust_gates_with_reused_controls", "error"
    ] = "running"
    owner_pid: int
    owner_token: str
    configuration: native.Pin
    started_utc: str
    finished_utc: str | None = None
    git_before: GitProof | None = None
    git_after: GitProof | None = None
    fd_before: Limits | None = None
    fd_after: Limits | None = None
    candidate_admitted: bool = False
    six_prior_semantic_controls_reused: bool = False
    source_and_binary_equal_to_candidate: bool = False
    command_journal: native.Pin | None = None
    rust_steps: list[native.Step] = Field(default_factory=list)
    metadata_steps: list[native.Step] = Field(default_factory=list)
    immutable_closure: bool = False
    all_owned_groups_absent: bool = False
    locks_released: bool = False
    repeated_allocator_probes: Literal[False] = False
    graph_or_OS_memory_qualified: Literal[False] = False
    errors: list[str] = Field(default_factory=list)

    @field_validator(
        "repeated_allocator_probes", "graph_or_OS_memory_qualified", mode="before"
    )
    @classmethod
    def literal_boolean(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("literal Boolean scope proof required")
        return value


class Wait(native.Record):
    outcome: Literal["running", "passed_actual_committed_owner_wait", "error"] = (
        "running"
    )
    configuration: native.Pin
    supervisor_pid: int
    owner_pid: int | None = None
    returncode: int | None = None
    waited: bool = False
    owner_group_absent: bool = False
    forced_cleanup: bool = False
    owner_receipt: native.Pin | None = None
    finished_utc: str | None = None
    errors: list[str] = Field(default_factory=list)
