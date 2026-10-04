"""Strict closed-control metadata; no engine, transport, or physical reader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator

import owner_models as o

HELPERS = {
    "owner_models.py",
    "oracle_models.py",
    "control_models.py",
    "control_admission.py",
    "control_io.py",
    "control_logs.py",
    "control_native.py",
    "qualify_control.py",
}
OWNER_MODELS_SHA = "6e06a814e5b379e8788326b8d9a18ff4d2b2c0087e1f91631f0f8cd123d56ef7"
ORACLE_MODELS_SHA = "39abf8b975401b55a155236bc741a1c541f10c1d768e2dcef9f82444956fd9a1"
ORACLE_FREEZE_SHA = "03ab34c5c1edaa844b4b395f06f55c630c6a29ba8741f640b7bf0892f9c51c64"
GENERIC_WAIT_SHA = "cfcad0454a8251dafc6ae499a66036d652606fc4974b0a13d4f6e06e53d749bc"
OWNER_HELPER_SHA = {
    "x1_models.py": OWNER_MODELS_SHA,
    "x1_io.py": "9783345d0be6e530c86b2b7a54d0f051918278c69ecb03ab3e3682a175f5a0ff",
    "x1_remote.py": "fe642d665e8c6630574d80515dcaa88d38db2cdf826947d5cde737dd80b4eab9",
    "x1_worker.py": "89a109320e66e140a731ed9a68b28c1483927e4b0d758128c4731cf4091b7b05",
    "x1_actions.py": "6617845928df0049899a42b3162240876e2f23737407f3e4e973c5b917ac1cba",
    "x1_owner.py": "4820f089f6985ffee2929e713fd1337d65a520a3c047951d1f38c02a9b8b5ea9",
}


class Config(o.Model):
    kind: Literal["tiny", "bfs-cap0", "host-pool-refusal"]
    producer: o.Pin
    original_wait: o.Pin
    canonical_wait: o.Pin
    oracle: o.Pin | None = None
    oracle_freeze: o.Pin | None = None
    output: Path
    helpers: dict[str, o.Pin]

    @model_validator(mode="after")
    def contract(self) -> Config:
        if set(self.helpers) != HELPERS:
            raise ValueError("complete local frozen helper set required")
        if (self.kind == "tiny") != (
            self.oracle is not None and self.oracle_freeze is not None
        ):
            raise ValueError("tiny requires the direct oracle02 receipt and freeze")
        if self.kind != "tiny" and (
            self.oracle is not None or self.oracle_freeze is not None
        ):
            raise ValueError("refusal controls have no physical result oracle")
        if not self.output.is_absolute() or ".." in self.output.parts:
            raise ValueError("absolute fresh output required")
        return self


class GenericWait(o.Model):
    outcome: str
    started_utc: str
    finished_utc: str | None
    configuration: str
    configuration_sha256: str
    waiter_source_sha256: str
    waiter_pid: int
    argv: list[str]
    child_pid: int | None
    child_pgid: int | None
    returncode: int | None
    wait_completed: bool
    child_group_absent: bool
    forced_cleanup: bool
    immutable_closure: bool
    errors: list[str]
    scope: str


class CanonicalOwnerWait(o.Model):
    observed_utc: str
    producer: o.Pin
    original_wait: o.Pin
    owner_pid: int = Field(gt=1)
    owner_pgid: int = Field(gt=1)
    actual_wait_completed: Literal[True]
    owner_group_absent: Literal[True]
    source_unchanged: Literal[True]
    returncode: Literal[0]
    all_recorded_owned_processes_absent: Literal[True]
    locks_released: Literal[True]


class Location(o.Model):
    log: o.Pin
    line: int = Field(ge=1)
    byte_offset: int = Field(ge=0)


class TaskKey(o.Model):
    job_id: int = Field(ge=0)
    stage: int = Field(ge=0)
    partition: int = Field(ge=0, lt=32)
    attempt: Literal[0]


class TaskStatus(o.Model):
    key: TaskKey
    worker_id: Literal[1, 2]
    status: str
    location: Location


class FailedReport(o.Model):
    key: TaskKey
    driver_id: int = Field(ge=0)
    sequence: int = Field(ge=0)
    message: str | None
    cause: dict[str, JsonValue]
    location: Location


class NativeRecord(o.Model):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    protocol: Literal[3]
    algorithm: Literal["bfs_reference"]
    operation_id: str
    snapshot_id: str
    generation: int = Field(ge=1)
    event: Literal["init", "decide", "apply", "result", "failure", "close"]
    partition: int = Field(ge=0, lt=32)
    worker_id: Literal[1, 2]
    pid: int = Field(gt=1)
    adjacency_id: int = Field(gt=0)
    job_id: int = Field(ge=0)
    session_id: str
    phase: int = Field(ge=0)
    location: Location


class NativeProof(o.Model):
    job_id: int
    session_id: str
    stages: list[int]
    owners: dict[int, NativeRecord]
    successful_tasks: int = 0
    cap_failures: list[NativeRecord] = Field(default_factory=list)
    both_workers: Literal[True] = True
    complete_topology: Literal[True] = True
    owners_closed: Literal[True] = True


class CauseWitness(o.Model):
    key: TaskKey
    worker_id: Literal[1, 2]
    pid: int
    session_id: str
    classified_cause: Literal["bfs_level_cap", "allocation_refused"]
    typed_cause: dict[str, JsonValue]
    native: Location | None = None
    execution: Location
    task_failure: Location
    driver_report: Location
    driver_failed_status: Location
    worker_failed_status: Location
    worker_byte_order_passed: Literal[True] = True
    driver_byte_order_passed: Literal[True] = True
    global_first_fault_claimed: Literal[False] = False


class Audit(o.Model):
    outcome: Literal[
        "checking",
        "passed_qualified_twohost_tiny_bfs_control",
        "passed_typed_bfs_cap_control",
        "passed_typed_host_pool_refusal_control",
        "error",
    ] = "checking"
    observed_utc: str
    configuration: o.Pin
    config: Config
    producer: o.Pin
    pins_before: list[o.Pin] = Field(default_factory=list)
    pins_after: list[o.Pin] = Field(default_factory=list)
    native: NativeProof | None = None
    witnesses: list[CauseWitness] = Field(default_factory=list)
    original_wait_adapter_passed: bool = False
    producer_source_process_closure_passed: bool = False
    both_physical_workers_executed: bool = False
    full_tiny_physical_oracle_passed: bool = False
    own_identity_closure_passed: bool = False
    qualification: o.Pin | None = None
    historical_cause_identified: Literal[False] = False
    full_original_graph_executed: Literal[False] = False
    errors: list[str] = Field(default_factory=list)
    scope: str = "Closed current stock4b control evidence only. Typed execution allocation refusal is a classification of the actual CommonErrorCause payload, not a new wire enum. No global first fault, native allocator participation in the plain range control, historical explanation, or full-scale result claim."
