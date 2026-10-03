"""Small native host reservation control, never an OS memory certificate."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Pin(Model):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class QuotaEvent(Model):
    timestamp_utc: str
    pid: int = Field(gt=0)
    id: int = Field(gt=0)
    event: Literal["admitted", "released"]
    extension: str
    bytes: int = Field(gt=0)
    pool_reserved: int = Field(ge=0)


class Identity(Model):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class Plan(Model):
    run_id: str = Field(pattern="^[a-z0-9-]+$")
    kind: Literal["native-quota-contention"] = "native-quota-contention"
    output: Path
    binary: Pin
    repo: Path
    source: str = Field(pattern="^[a-f0-9]{40}$")
    tree: str = Field(pattern="^[a-f0-9]{40}$")
    extension_repo: Path
    extension_source: str = Field(pattern="^[a-f0-9]{40}$")
    extension_tree: str = Field(pattern="^[a-f0-9]{40}$")
    helpers: list[Pin]
    client: list[Pin]
    partitions: Literal[16] = 16
    threads: Literal[16] = 16
    worker_count: Literal[0] = 0
    pool_bytes_per_process: Literal[201326592] = 201326592
    native_quota_bytes: Literal[134217728] = 134217728
    native_package_identity: str = Field(pattern="^nutmeg@0\\.1\\.0:[a-f0-9]{64}$")
    timeout_seconds: int = Field(default=300, ge=60, le=900)


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
    endpoint: str | None = None
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
    session_ids: dict[str, str] = Field(default_factory=dict)
    native_audit: Pin | None = None
    accounting_scope: str = "local native prepaid host lease; allocations within native quota; no total RSS, OS quota, PSS, spill, transport accounting"
