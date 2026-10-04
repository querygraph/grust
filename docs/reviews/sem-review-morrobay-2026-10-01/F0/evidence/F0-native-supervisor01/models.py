"""Native F0 one-shot protocol; no CSR topology qualification is claimed."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

SOURCE = "796b24be244f068554f885cfa33ff2d745c75682"
ORDER = ("cit-directed", "cit-undirected", "graph500-directed", "graph500-undirected")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FilePin(Identity):
    path: Path

    @model_validator(mode="after")
    def absolute(self) -> FilePin:
        if not self.path.is_absolute():
            raise ValueError("absolute pinned file path required")
        return self


class Dataset(Record):
    name: Literal["cit-Patents", "graph500-24"]
    vertices: FilePin
    edges: FilePin
    evidence: FilePin
    vertex_rows: int = Field(gt=0, lt=2**32)
    edge_rows: int = Field(gt=0)

    @model_validator(mode="after")
    def originals(self) -> Dataset:
        counts = {"cit-Patents": (3774768, 16518947), "graph500-24": (8870942, 260379520)}
        if (self.vertex_rows, self.edge_rows) != counts[self.name]:
            raise ValueError("exact retained original dataset counts required")
        return self


class SourceManifest(Record):
    observed_utc: str
    source_commit: Literal["796b24be244f068554f885cfa33ff2d745c75682"]
    source_prefix: str
    files: dict[str, Identity]
    git_blobs: dict[str, str]
    scope: str


class Config(Record):
    phase: Literal["cells"] = "cells"
    source_commit: Literal["796b24be244f068554f885cfa33ff2d745c75682"] = "796b24be244f068554f885cfa33ff2d745c75682"
    source_root: Path
    source_files: tuple[FilePin, ...]
    helper_files: tuple[FilePin, ...]
    output: Path
    lock: Path
    refuse_locks: tuple[Path, ...]
    cargo: FilePin
    rustc: FilePin
    time: FilePin
    ps: FilePin
    build_receipt: FilePin | None = None
    binary: FilePin | None = None
    datasets: tuple[Dataset, ...] = ()
    ssd_root: Path
    cell_seconds: int = Field(default=600, ge=1, le=3600)
    closure_seconds: int = Field(default=15, ge=1, le=60)
    disk_free_bytes: int = Field(default=10 * 2**30, ge=2**20)

    @model_validator(mode="after")
    def scope(self) -> Config:
        paths = (self.source_root, self.output, self.lock, self.ssd_root, *self.refuse_locks)
        if any(not path.is_absolute() for path in paths):
            raise ValueError("all protocol paths must be absolute")
        required = {"README.md", "runs.jsonl", "runs-binary-search.jsonl",
                    "csr-floor/Cargo.toml", "csr-floor/Cargo.lock", "csr-floor/src/main.rs"}
        if {pin.path.relative_to(self.source_root).as_posix() for pin in self.source_files} != required:
            raise ValueError("exact six borrowed source files required")
        if len({pin.path for pin in self.source_files}) != 6 or not self.helper_files:
            raise ValueError("unique source and nonempty helper inventory required")
        if self.binary is None or self.build_receipt is None:
            raise ValueError("sealed successful build receipt and binary required")
        if tuple(data.name for data in self.datasets) != ("cit-Patents", "graph500-24"):
            raise ValueError("both datasets in fixed order required")
        for data in self.datasets:
            for pin in (data.vertices, data.edges):
                if not pin.path.is_relative_to(self.ssd_root):
                    raise ValueError("timed Parquet inputs must be on declared internal SSD root")
        return self

    def pins(self) -> tuple[FilePin, ...]:
        extra = tuple(pin for pin in (self.build_receipt, self.binary) if pin is not None)
        inputs = tuple(pin for data in self.datasets for pin in (data.vertices, data.edges, data.evidence))
        return (*self.source_files, *self.helper_files, self.cargo, self.rustc,
                self.time, self.ps, *extra, *inputs)


class RootBuild(Record):
    started_utc: str
    finished_utc: str
    outcome: Literal["passed_optimized_native_F0_build"]
    owner_pid: int = Field(gt=0)
    cargo_pid: int = Field(gt=0)
    errors: list[str]
    source_before: dict[str, FilePin]
    source_after: dict[str, FilePin]
    cargo_version: str
    rustc_verbose: str
    environment: dict[str, str]
    command: tuple[str, ...]
    returncode: Literal[0]
    binary: FilePin
    file_type: str
    locks_released: Literal[True]


class NativeResult(Record):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    vertices: int = Field(ge=0)
    edges: int = Field(ge=0)
    arcs: int = Field(ge=0)
    undirected: bool
    target_bits: Literal[32]
    id_mapping: Literal["identity", "direct table", "binary search"]
    threads: Literal[4]
    read_seconds: float = Field(ge=0)
    map_seconds: float = Field(ge=0)
    build_seconds: float = Field(ge=0)
    total_seconds: float = Field(ge=0)
    max_degree: int = Field(ge=0)
    csr_bytes: int = Field(ge=0)


class Child(Record):
    id: str
    command: tuple[str, ...]
    outcome: Literal["running", "passed_internal_guard", "error", "skipped"]
    started_utc: str | None = None
    finished_utc: str | None = None
    pid: int | None = None
    returncode: int | None = None
    launch_to_wait_seconds: float | None = None
    timed_out: bool = False
    forced_cleanup: bool = False
    group_remaining: tuple[str, ...] = ()
    stdout: Identity | None = None
    stderr: Identity | None = None
    time_record: Identity | None = None
    maxrss_bytes: int | None = None
    result: NativeResult | None = None
    error: str | None = None


class Receipt(Record):
    config: Config
    config_pin: FilePin
    helper_pin: FilePin
    started_utc: str
    finished_utc: str | None = None
    parent_pid: int
    outcome: Literal["running", "built", "completed_internal_guards", "error"] = "running"
    before: dict[str, Identity] = Field(default_factory=dict)
    after: dict[str, Identity] = Field(default_factory=dict)
    children: list[Child] = Field(default_factory=list)
    binary: FilePin | None = None
    observations: dict[str, JsonValue] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    locks_released: bool = False
    full_topology_oracle: Literal[False] = False
    checksum_scope: Literal["source internal target-sum assertion only"] = "source internal target-sum assertion only"
    shared_host: Literal[True] = True
    os_resource_caps: Literal[False] = False
