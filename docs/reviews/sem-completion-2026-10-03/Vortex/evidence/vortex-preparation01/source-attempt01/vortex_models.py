"""Strict admission and observations for a tiny native Vortex capability control."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FilePin(Record):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Plan(Record):
    mode: Literal["native_unregistered", "registered_reader"]
    output_root: Path
    binary: Path
    venv: Path
    python_home: Path
    python_purelib: Path
    python_library_directory: Path
    adapter_python_root: Path | None = None
    pins: list[FilePin] = Field(min_length=4)
    runtime_source: Literal["9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"]
    adapter_source: Literal["4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"]
    timeout_seconds: Literal[180] = 180
    threads: Literal[2] = 2
    sail_pool_bytes: Literal[536870912] = 536870912

    @model_validator(mode="after")
    def admission(self) -> Plan:
        paths = [self.output_root, self.binary, self.venv, self.python_home,
                 self.python_purelib, self.python_library_directory]
        paths += [pin.path for pin in self.pins]
        if self.adapter_python_root is not None:
            paths.append(self.adapter_python_root)
        if any(not path.is_absolute() for path in paths):
            raise ValueError("all declared paths must be absolute")
        if len({pin.path.resolve() for pin in self.pins}) != len(self.pins):
            raise ValueError("duplicate pinned physical path")
        if self.mode == "registered_reader" and self.adapter_python_root is None:
            raise ValueError("registered reader needs its exact source Python root")
        if not self.python_purelib.is_relative_to(self.venv):
            raise ValueError("purelib must belong to the dedicated venv")
        return self


class Error(Record):
    phase: str
    type: str
    message: str


class Attempt(Record):
    name: str
    outcome: Literal["started", "completed", "error", "not_admitted"] = "started"
    directory: Path | None = None
    error: Error | None = None


class PhysicalCheck(Record):
    name: str
    directory: Path
    rows: int
    expected_rows: int
    physical_schemas: list[str]
    full_typed_rows_passed: bool
    files: list[FilePin]


class ServerExit(Record):
    pid: int
    pgid: int
    argv: list[str]
    launched_utc: str
    closed_utc: str | None = None
    termination_requested: bool = False
    forced_cleanup: bool = False
    returncode: int | None = None
    wait_completed: bool = False
    group_absent: bool = False


class Receipt(Record):
    outcome: Literal["running", "passed_native_format_control", "passed_registered_reader_control",
                     "not_admitted", "error", "timeout"] = "running"
    started_utc: str
    finished_utc: str | None = None
    configuration: FilePin
    plan: Plan
    owner_pid: int
    python_version: str
    pyspark_version: str
    pyarrow_version: str
    vortex_version: str | None = None
    adapter_import_error: str | None = None
    environment: dict[str, str]
    identities_before: list[FilePin] = Field(default_factory=list)
    identities_after: list[FilePin] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    physical_checks: list[PhysicalCheck] = Field(default_factory=list)
    server: ServerExit | None = None
    raw_inventory: list[FilePin] = Field(default_factory=list)
    errors: list[Error] = Field(default_factory=list)
    scope: str = ("Tiny native local capability control; software pool is not an OS cap. "
                  "No graph timing, sorted-layout or checkpoint-performance claim. "
                  "Writer/read errors retain their observed type and text; unsupported is not inferred from arbitrary errors.")
