"""Owned native X2 controls; successful controls do not diagnose historical loss."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Pin(Model):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class Identity(Model):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class FixtureManifest(Model):
    schema_version: Literal[1]
    vertex_rows: Literal[4096]
    edge_rows: Literal[4097]
    fragment_count: Literal[8]
    signed_high_bit_ids: Literal[True]
    source: Literal[0]
    directed: Literal[False]
    reachable: Literal[4095]
    max_hops: Literal[11]
    files: dict[str, Identity]


class Plan(Model):
    run_id: str = Field(pattern="^[a-z0-9-]+$")
    kind: Literal["reference", "pool-refusal"]
    output: Path
    binary: Pin
    repo: Path
    source: str = Field(pattern="^[a-f0-9]{40}$")
    tree: str = Field(pattern="^[a-f0-9]{40}$")
    fixture: Path
    fixture_manifest: Pin
    originals: list[Pin]
    helpers: list[Pin]
    client: list[Pin]
    partitions: Literal[16]
    threads: Literal[16] = 16
    worker_count: Literal[2] = 2
    worker_task_slots: Literal[9] = 9
    pool_bytes_per_process: Literal[10737418240, 1048576]
    timeout_seconds: int = Field(default=300, ge=60, le=900)

    @model_validator(mode="after")
    def slots_admit_declared_reference_write_region(self) -> "Plan":
        if (
            self.worker_count * self.worker_task_slots < self.partitions + 1
            or self.worker_task_slots >= self.partitions
        ):
            raise ValueError(
                "P16 requires observed17-slot region admission and each worker below16 slots"
            )
        expected_pool = 10737418240 if self.kind == "reference" else 1048576
        if self.pool_bytes_per_process != expected_pool:
            raise ValueError(
                "reference requires 10GiB; refusal requires explicit 1MiB greedy pools"
            )
        return self


class SessionBootstrap(Model):
    kind: Literal["AnalyzePlan.spark_version"] = "AnalyzePlan.spark_version"
    started_utc: str
    finished_utc: str
    seconds: float
    spark_version: str
    server_log_start: int
    server_log_end: int


class WorkerReadiness(Model):
    started_utc: str
    finished_utc: str
    seconds: float
    server_log_end: int
    worker_ids: list[int]
    worker_pids: list[int]
    identity_files: list[Pin]
    no_dataset_job_before_readiness: Literal[True] = True


class Action(Model):
    name: str
    started_utc: str
    finished_utc: str | None = None
    seconds: float | None = None
    server_log_start: int
    server_log_end: int | None = None
    worker_log_start: dict[str, int] = Field(default_factory=dict)
    worker_log_end: dict[str, int] = Field(default_factory=dict)
    raw_rows: list[list[int]] = Field(default_factory=list)
    raw_schema: list[tuple[str, str]] = Field(default_factory=list)
    error: str | None = None
    expected_error: bool = False


class ProcessRow(Model):
    pid: int
    ppid: int
    pgid: int
    rss_kib: int
    resident_size_bytes: int | None = None
    physical_footprint_bytes: int | None = None
    process_start_abstime: int | None = None
    physical_observation_error: str | None = None


class Sample(Model):
    observed_utc: str
    monotonic_seconds: float
    processes: list[ProcessRow]


class Receipt(Model):
    schema_version: Literal[1] = 1
    outcome: Literal["checking", "completed_unqualified", "error"] = "checking"
    configuration: Plan
    configuration_pin: Pin
    started_utc: str
    finished_utc: str | None = None
    owner_pid: int
    server_pid: int | None = None
    admitted_environment: Pin | None = None
    worker_readiness: WorkerReadiness | None = None
    session_bootstrap: SessionBootstrap | None = None
    server_returncode: int | None = None
    server_wait_completed: bool = False
    shutdown_sigint: bool = False
    shutdown_sigkill: bool = False
    server_group_absent: bool = False
    worker_pids: list[int] = Field(default_factory=list)
    worker_groups_absent: bool = False
    actions: list[Action] = Field(default_factory=list)
    inputs_before: dict[str, Pin] = Field(default_factory=dict)
    inputs_after: dict[str, Pin] = Field(default_factory=dict)
    source_before: dict[str, str] = Field(default_factory=dict)
    source_after: dict[str, str] = Field(default_factory=dict)
    rss_samples: list[Sample] = Field(default_factory=list)
    sampler_error: str | None = None
    resource_scope: str = "per-PID sampled RSS and proc_pid_rusage footprint; no OS quota, unique physical memory, or OS peak claim"
    full_server_phase_attribution: Literal[False] = False
    full_physical_output_qualified: Literal[False] = False
    errors: list[str] = Field(default_factory=list)
    traceback: str | None = None
    evidence_queries: dict[str, str] = Field(default_factory=dict)
    evidence_query_errors: dict[str, str] = Field(default_factory=dict)
    graph_iterations: int | None = None
    graph_converged: bool | None = None
    graph_events: Pin | None = None
    historical_original_cause: Literal["unexplained"] = "unexplained"
