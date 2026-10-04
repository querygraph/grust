"""Typed records for separately declared native X2 diagnostic controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class ReferenceRow:
    id: int
    distance: float | None
    hops: int | None
    parent: int | None


@dataclass(frozen=True, slots=True)
class Arguments:
    endpoint: str
    case: Literal["functional", "pool-refusal"]
    fixture: Path
    output: Path
    partitions: int


@dataclass(slots=True)
class Receipt:
    observed_utc: str
    arguments: Arguments
    status: str = "running"
    query_start_utc: str | None = None
    query_end_utc: str | None = None
    pipeline_seconds: float | None = None
    iterations: int | None = None
    converged: bool | None = None
    error: str | None = None
    session_stopped: bool = False


@dataclass(frozen=True, slots=True)
class FilePin:
    path: str
    bytes: int
    sha256: str


@dataclass(slots=True)
class OracleReceipt:
    observed_utc: str
    status: str = "unqualified"
    rows: int = 0
    reachable: int = 0
    max_hops: int = 0
    mismatches: int = 0
    before: list[FilePin] = field(default_factory=list)
    after: list[FilePin] = field(default_factory=list)
    error: str | None = None
