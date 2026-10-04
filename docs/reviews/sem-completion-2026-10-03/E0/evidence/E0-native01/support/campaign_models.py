"""Frozen identities and typed observations for nine serial native E0 cells."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003/E0-native01")
SOURCE = Path("/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/e0-native-f2b297fc")
COMMIT = "f2b297fc8443221891ce5f4afe88f955ed125b38"
TREE = "3395c493c98edebc4ca137ea81d7fa25dadd8979"
RUNTIME_COMMIT = "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"
BINARY = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/sail-target/release/sail")
BINARY_SHA256 = "ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e"
VENV = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-int64-build01/venv")
PYHOME = Path("/Users/alexy/.asdf/installs/python/3.12.6")
LOCK = Path("/tmp/morrobay-sem-completion-heavy.lock")
DATA = Path("/Users/alexy/src/grust-benchmark-data")
OFFICIAL = Path("/Volumes/Apo/graph-tests/data/ldbc-20261003")


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    source: int
    undirected: bool
    weighted: bool
    source_basis: str


DATASETS = (
    Dataset("cit-Patents", 1, False, False, "selected source 1; not an official source or earlier A6 claim"),
    Dataset("kgs", 239044, True, True, "official kgs.properties BFS/SSSP source"),
    Dataset("wiki-Talk", 2, False, False, "official wiki-Talk.properties BFS source; unit-weight SSSP adaptation"),
)
PROGRAMS = ("pagerank", "sssp", "landmarks")


@dataclass(frozen=True, slots=True)
class FilePin:
    path: str
    bytes: int
    sha256: str


@dataclass(slots=True)
class Process:
    role: str
    argv: list[str]
    pid: int
    pgid: int
    started_utc: str
    finished_utc: str | None = None
    returncode: int | None = None
    actual_wait_completed: bool = False
    requested_termination: bool = False
    forced_kill: bool = False
    group_absent: bool = False


@dataclass(slots=True)
class Cell:
    dataset: Dataset
    program: str
    status: str = "pending"
    processes: list[Process] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    client_launch_wait_seconds: float | None = None
    input_before: list[FilePin] = field(default_factory=list)
    input_after: list[FilePin] = field(default_factory=list)
    raw_inventory: list[FilePin] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Receipt:
    started_utc: str
    owner_pid: int
    owner_pgid: int
    source_commit: str = COMMIT
    source_tree: str = TREE
    runtime_commit: str = RUNTIME_COMMIT
    outcome: str = "running"
    finished_utc: str | None = None
    binary_before: FilePin | None = None
    binary_after: FilePin | None = None
    source_before: list[FilePin] = field(default_factory=list)
    source_after: list[FilePin] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)
    all_child_groups_absent: bool = False
    source_unchanged: bool = False
    lock_released: bool = False
    qualified_cells: int = 0
    errors: list[str] = field(default_factory=list)
