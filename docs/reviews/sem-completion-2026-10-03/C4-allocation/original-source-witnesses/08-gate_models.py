"""Typed candidate/final source contracts for a root-launched native Rust gate."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
LOCK_BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
BASE_COMMIT = "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"
CANDIDATE_TREE = "6d290a1d983ebec74bffff33cfdf7820622e4223"
REQUIRED_TOOLS = {
    "cargo",
    "rustc",
    "rustfmt",
    "cargo-fmt",
    "clippy-driver",
    "cargo-clippy",
    "protoc",
}


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Pin(Identity):
    path: Path

    @model_validator(mode="after")
    def absolute(self) -> Pin:
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("absolute safe pin path required")
        return self


class Source(Record):
    head: str
    head_tree: str
    admitted_tree: str
    status: str
    detached: bool


class NamespaceAdmission(Record):
    observed_utc: str
    outcome: Literal["prepared_private_native_gate_namespace"]
    target: Path
    cargo_home: Path
    seed_manifests: list[Pin] = Field(min_length=1)
    seed_copy_verified: Literal[True]
    credentials_and_configuration_excluded: Literal[True]
    scope: str


class Plan(Record):
    mode: Literal["candidate", "committed"]
    root: Path
    repo: Path
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree: Literal["6d290a1d983ebec74bffff33cfdf7820622e4223"]
    target: Path
    cargo_home: Path
    namespace_admission: Pin
    source_files: dict[str, Identity]
    helpers: dict[str, Identity]
    tools: dict[str, Pin]
    python: Pin
    libpython: Pin
    minimum_free_bytes: int = Field(default=40 * 2**30, ge=40 * 2**30)
    emergency_free_bytes: int = Field(default=20 * 2**30, ge=20 * 2**30)
    maximum_target_bytes: int = Field(default=200 * 2**30, ge=2**30, le=200 * 2**30)
    total_seconds: int = Field(default=21600, ge=60, le=43200)
    step_seconds: int = Field(default=10800, ge=30, le=21600)

    @model_validator(mode="after")
    def scope(self) -> Plan:
        paths = (self.root, self.repo, self.target, self.cargo_home)
        if any(not p.is_absolute() or ".." in p.parts for p in paths):
            raise ValueError("absolute safe namespace paths required")
        if self.root.parent != BASE or not self.root.name.startswith("C2-observer-build-"):
            raise ValueError("fresh named observer build attempt under the completion root required")
        if self.repo.parent != Path("/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003"):
            raise ValueError("isolated completion worktree required")
        if len(set(paths)) != 4 or any(a in b.parents for a in paths for b in paths if a != b):
            raise ValueError("source/result/target/cache namespaces must be disjoint")
        allowed = (
            BASE,
            Path("/Users/alexy/src/grust-benchmark-builds/sem-completion-20261003"),
        )
        if any(not any(a in p.parents for a in allowed) for p in (self.target, self.cargo_home)):
            raise ValueError("private Apo or SSD build namespaces required")
        if self.mode == "candidate" and self.commit != BASE_COMMIT:
            raise ValueError("candidate must remain detached at the admitted base")
        if self.mode == "committed" and self.commit == BASE_COMMIT:
            raise ValueError("final gate requires the actual observer commit")
        if self.emergency_free_bytes >= self.minimum_free_bytes:
            raise ValueError("emergency disk floor must be below pre-step admission floor")
        if set(self.tools) != REQUIRED_TOOLS or set(self.helpers) != {
            "gate_models.py",
            "gate_owner.py",
            "wait_launch.py",
        }:
            raise ValueError("complete native tool/helper pins required")
        if not {"Cargo.toml", "Cargo.lock"} <= set(self.source_files):
            raise ValueError("workspace Cargo manifest/lock pins required")
        if any(Path(n).is_absolute() or ".." in Path(n).parts for n in self.source_files):
            raise ValueError("safe relative source pin names required")
        if self.python.path != Path("/Users/alexy/.asdf/installs/python/3.12.6/bin/python3.12"):
            raise ValueError("admitted Python 3.12.6 required")
        if self.libpython.path != Path("/Users/alexy/.asdf/installs/python/3.12.6/lib/libpython3.12.dylib"):
            raise ValueError("admitted Python shared library required")
        rust_directory = self.tools["rustc"].path.parent
        if any(self.tools[n].path.parent != rust_directory for n in REQUIRED_TOOLS - {"protoc"}):
            raise ValueError("all Rust tools must come from one admitted toolchain bin directory")
        return self


class Owner(Record):
    pid: int
    token: str
    plan_sha256: str


class Step(Record):
    name: str
    argv: list[str]
    started_utc: str
    pid: int
    pgid: int
    log: Path
    returncode: int | None = None
    wait_completed: bool = False
    finished_utc: str | None = None
    remaining_owned_pids: list[int] = Field(default_factory=list)
    forced_cleanup: bool = False


class Receipt(Record):
    outcome: Literal[
        "running",
        "passed_candidate_native_gate",
        "passed_committed_native_gate",
        "error",
    ] = "running"
    started_utc: str
    finished_utc: str | None = None
    owner: Owner
    configuration: Pin
    mode: Literal["candidate", "committed"]
    source_before: Source | None = None
    source_after: Source | None = None
    immutable_pins_before_after_equal: bool = False
    free_bytes_before: dict[str, int] = Field(default_factory=dict)
    target_bytes_before: int | None = None
    target_bytes_after: int | None = None
    namespace_admission: Pin
    release_environment: dict[str, str] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    binary: Pin | None = None
    all_owned_groups_absent: bool = False
    locks_released: bool = False
    errors: list[str] = Field(default_factory=list)
    scope: str = "Exact admitted source Rust gates and optimized native artifact; no observer collector, engine or benchmark qualification."
