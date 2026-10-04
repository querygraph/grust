"""Standalone factory gates and allocator controls; no Sail OS-envelope claim."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Pin(Record):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def safe_path(self) -> "Pin":
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("absolute safe pin path required")
        return self


class Plan(Record):
    root: Path
    source: Path
    source_freeze: Pin
    source_files: dict[str, Pin]
    source_origins: list[Pin] = Field(min_length=7)
    helpers: dict[str, Pin]
    ownership_helpers: dict[str, Pin]
    target: Path
    cargo_home: Path
    seed_manifests: list[Pin] = Field(min_length=1)
    tools: dict[str, Pin]
    total_seconds: int = Field(default=14400, ge=300, le=21600)
    step_seconds: int = Field(default=7200, ge=30, le=10800)
    probe_seconds: int = Field(default=600, ge=10, le=1800)
    minimum_free_bytes: int = Field(default=40 * 2**30, ge=40 * 2**30)
    emergency_free_bytes: int = Field(default=20 * 2**30, ge=20 * 2**30)

    @model_validator(mode="after")
    def namespaces(self) -> "Plan":
        base = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
        if self.root.parent != base or not self.root.name.startswith(
            "C4-allocation-run"
        ):
            raise ValueError(
                "fresh C4 native attempt under the completion root required"
            )
        paths = (self.root, self.source, self.target, self.cargo_home)
        if any(not path.is_absolute() or ".." in path.parts for path in paths):
            raise ValueError("absolute safe namespaces required")
        if len(set(paths)) != 4 or any(
            a in b.parents for a in paths for b in paths if a != b
        ):
            raise ValueError("source/result/target/cache must be disjoint")
        if set(self.tools) != {
            "cargo",
            "rustc",
            "rustfmt",
            "cargo-fmt",
            "clippy-driver",
            "cargo-clippy",
        }:
            raise ValueError("complete admitted Rust toolchain pins required")
        if set(self.helpers) != {
            "allocator_models.py",
            "allocator_owner.py",
            "wait_allocator.py",
        } or set(self.ownership_helpers) != {"gate_models.py", "gate_owner.py"}:
            raise ValueError("exact new and reused ownership helper pins required")
        if self.emergency_free_bytes >= self.minimum_free_bytes:
            raise ValueError("active disk floor must be below admission floor")
        return self


class Step(Record):
    name: str
    argv: list[str]
    pid: int
    pgid: int
    started_utc: str
    finished_utc: str | None = None
    returncode: int | None = None
    waited: bool = False
    group_absent: bool = False
    forced_cleanup: bool = False
    cleanup_errors: list[str] = Field(default_factory=list)
    log: Pin | None = None


class Receipt(Record):
    outcome: Literal[
        "running", "passed_native_factory_allocation_controls", "error"
    ] = "running"
    owner_pid: int
    owner_token: str
    configuration: Pin
    started_utc: str
    finished_utc: str | None = None
    steps: list[Step] = Field(default_factory=list)
    binary: Pin | None = None
    immutable_source_tool_helper_closure: bool = False
    all_owned_groups_absent: bool = False
    locks_released: bool = False
    errors: list[str] = Field(default_factory=list)
    scope: str = "Copied native9f compact factory versus ordered DF55 min_by; requested System bytes/counts and separate process-lifetime RSS, exploratory shared native host, no graph/OS-cap/physical-pool claim"


class Launch(Record):
    outcome: Literal["running", "passed_waited_native_factory_controls", "error"] = (
        "running"
    )
    configuration: Pin
    launcher_pid: int
    owner_pid: int | None = None
    argv: list[str]
    returncode: int | None = None
    waited: bool = False
    owner_group_absent: bool = False
    forced_cleanup: bool = False
    owner_receipt: Pin | None = None
    finished_utc: str | None = None
    errors: list[str] = Field(default_factory=list)
