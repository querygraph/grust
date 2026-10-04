"""Root-sealed native two-host cases, with current reproduction provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

SOURCE = "4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"
HELPERS = {
    "x1_models.py",
    "x1_io.py",
    "x1_remote.py",
    "x1_worker.py",
    "x1_actions.py",
    "x1_owner.py",
}
LOGGING = "info,sail_execution::task_runner::actor::handler=debug,sail_execution::driver::server=debug,sail_execution::diagnostics=warn,tonic::transport::server=debug"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def exact_literals(cls, value: object) -> object:
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                args = get_args(field.annotation)
                if name in value and get_origin(field.annotation) is Literal:
                    if (
                        args
                        and all(type(item) is bool for item in args)
                        and type(value[name]) is not bool
                    ):
                        raise ValueError(
                            "literal boolean proof must be an actual boolean"
                        )
                    if (
                        args
                        and all(type(item) is int for item in args)
                        and type(value[name]) is not int
                    ):
                        raise ValueError(
                            "literal numeric protocol value must be an actual integer"
                        )
            if (
                "worker_id" in value
                and value["worker_id"] is not None
                and type(value["worker_id"]) is not int
            ):
                raise ValueError("worker identity must be an actual integer")
        return value


class Pin(Model):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def absolute(self) -> Pin:
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("absolute safe immutable pin required")
        return self


class Ssh(Model):
    host: Literal["alexy@192.168.4.61", "alexy@192.168.4.63"]
    identity_file: Path
    host_key_alias: Literal["capitola", "morrobay-sem-native"]
    known_hosts: Pin | None = None
    admission: Pin

    @model_validator(mode="after")
    def paths(self) -> Ssh:
        if not self.identity_file.is_absolute() or ".." in self.identity_file.parts:
            raise ValueError("absolute caller-local key reference required")
        return self


class Target(Model):
    name: Literal["morrobay", "capitola"]
    architecture: Literal["x86_64", "arm64"]
    advertise: Literal["192.168.4.63", "192.168.4.61"]
    ssh: Ssh
    repo: Path
    tree: str = Field(pattern="^[a-f0-9]{40}$")
    python: Path
    python_version: Literal["3.12.6", "3.12.8"]
    python_pin: Pin
    python_library: Pin
    client_files: list[Pin] = Field(min_length=2)
    binary: Pin
    wheel: Pin
    helpers: dict[str, Pin]
    identity_helper: Pin
    assembly_receipt: Pin
    provenance: list[Pin] = Field(min_length=2)
    environment_file: Path

    @model_validator(mode="after")
    def contract(self) -> Target:
        expected = (
            ("x86_64", "192.168.4.63")
            if self.name == "morrobay"
            else ("arm64", "192.168.4.61")
        )
        alias = "morrobay-sem-native" if self.name == "morrobay" else "capitola"
        if (
            (self.architecture, self.advertise) != expected
            or self.ssh.host != "alexy@" + self.advertise
            or self.ssh.host_key_alias != alias
        ):
            raise ValueError("native physical host/address/SSH mapping differs")
        if self.python_version != ("3.12.6" if self.name == "morrobay" else "3.12.8"):
            raise ValueError("explicit admitted native CPython patch versions differ")
        if self.name == "morrobay" and self.ssh.known_hosts is None:
            raise ValueError(
                "admitted private public-known-host inventory required for reverse route"
            )
        if set(self.helpers) != HELPERS or any(
            p.path.name != n for n, p in self.helpers.items()
        ):
            raise ValueError("full exact supervisor helper set required")
        if len({p.path.parent for p in self.helpers.values()}) != 1:
            raise ValueError("all host helpers must share one admitted directory")
        if any(
            not p.is_absolute() or ".." in p.parts
            for p in (self.repo, self.python, self.environment_file)
        ):
            raise ValueError(
                "safe absolute source/interpreter/secret-file reference required"
            )
        return self


class Dataset(Model):
    name: Literal["signed-tiny", "generated-graph500-scale24"]
    vertices: str
    edges: str
    vertex_column: str = "id"
    source_column: str = "src"
    target_column: str = "dst"
    source_vertex: int
    expected_vertices: int = Field(ge=1)
    expected_edges: int = Field(ge=1)
    admissions: dict[Literal["morrobay", "capitola"], Pin]

    @model_validator(mode="after")
    def hosts(self) -> Dataset:
        if set(self.admissions) != {"morrobay", "capitola"}:
            raise ValueError("both actual input admissions required")
        if not -(2**63) <= self.source_vertex <= 2**63 - 1:
            raise ValueError("signed original source required")
        return self


class PriorControl(Model):
    kind: Literal["tiny", "bfs-cap0", "host-pool-refusal"]
    producer: Pin
    qualification: Pin
    expected_outcome: Literal[
        "passed_full_undirected_BFS_certificate",
        "passed_typed_bfs_cap_control",
        "passed_typed_host_pool_refusal_control",
    ]

    @model_validator(mode="after")
    def outcome(self) -> PriorControl:
        expected = {
            "tiny": "passed_full_undirected_BFS_certificate",
            "bfs-cap0": "passed_typed_bfs_cap_control",
            "host-pool-refusal": "passed_typed_host_pool_refusal_control",
        }
        if self.expected_outcome != expected[self.kind]:
            raise ValueError("exact preceding control qualification required")
        return self


class Plan(Model):
    run_id: str = Field(pattern="^x1-native-[a-z0-9-]+$")
    root: Path
    kind: Literal["tiny", "bfs-cap0", "host-pool-refusal", "scale24"]
    driver: Target
    worker1: Target
    worker2: Target
    dataset: Dataset
    remote_root: Path
    output_uri: str = Field(pattern="^s3://[a-z0-9-]+/[a-z0-9/_-]+$")
    storage_endpoint: str = Field(
        pattern="^http://192[.]168[.]4[.]61:(39000|49[1-9][0-9]{2})$"
    )
    storage_admission: Pin
    connect_port: int = Field(default=50151, ge=1024, le=65535)
    gateway_port: int = Field(default=50152, ge=1024, le=65535)
    worker_ports: tuple[int, int] = (50162, 50161)
    max_levels: Literal[0, 8]
    partitions: Literal[32] = 32
    threads: Literal[8] = 8
    worker_task_slots: Literal[48] = 48
    native_quota_bytes: Literal[17179869184] = 17179869184
    normal_pool_bytes: Literal[34359738368] = 34359738368
    max_phase_budget: Literal[32] = 32
    batch_rows: Literal[4096] = 4096
    stream_creation_timeout_seconds: Literal[900] = 900
    worker_idle_seconds: Literal[86400] = 86400
    timeout_seconds: int = Field(default=3600, ge=120, le=21600)
    lease_seconds: Literal[15] = 15
    keepalive_interval_seconds: int = Field(default=60, ge=1, le=3600)
    keepalive_timeout_seconds: int = Field(default=10, ge=1, le=3600)
    prior_controls: list[PriorControl] = Field(default_factory=list)
    historical_missing_receipt: Pin

    @field_validator("worker_ports", mode="before")
    @classmethod
    def json_worker_ports(cls, value: object, info: ValidationInfo) -> object:
        if info.mode == "json" and isinstance(value, list):
            if len(value) != 2 or any(type(port) is not int for port in value):
                raise ValueError("JSON worker ports require exactly two integers")
            return tuple(value)
        return value

    @model_validator(mode="after")
    def envelope(self) -> Plan:
        for root, target in (
            (self.root, self.worker1),
            (self.remote_root, self.driver),
        ):
            if (
                not root.is_absolute()
                or ".." in root.parts
                or root == target.repo
                or target.repo in root.parents
            ):
                raise ValueError("fresh absolute case roots outside sources required")
            protected = [
                target.environment_file,
                *[item.path for item in target.helpers.values()],
            ]
            if any(path == root or root in path.parents for path in protected):
                raise ValueError(
                    "evidence root must not own immutable helpers or secrets"
                )
        if (
            self.driver.name != "capitola"
            or self.worker1.name != "morrobay"
            or self.worker2 != self.driver
        ):
            raise ValueError("driver/worker1/worker2 physical mapping differs")
        if len({self.connect_port, self.gateway_port, *self.worker_ports}) != 4:
            raise ValueError("distinct owned listener ports required")
        if any(not 1024 <= port <= 65535 for port in self.worker_ports):
            raise ValueError("valid explicit worker ports required")
        if (
            self.driver.binary.sha256 != self.worker1.binary.sha256
            or self.driver.binary.bytes != self.worker1.binary.bytes
        ):
            raise ValueError("same fat CLI bytes required on both hosts")
        if (
            self.driver.wheel.sha256 != self.worker1.wheel.sha256
            or self.driver.wheel.bytes != self.worker1.wheel.bytes
        ):
            raise ValueError("same fat wheel bytes required on both hosts")
        if any(
            self.driver.helpers[n].sha256 != self.worker1.helpers[n].sha256
            for n in HELPERS
        ):
            raise ValueError("same helper bodies required on both hosts")
        if (
            self.run_id not in self.output_uri
            or self.root.name != self.run_id
            or self.remote_root.name != self.run_id
        ):
            raise ValueError("fresh run-bound metadata/store namespaces required")
        if self.max_levels != (0 if self.kind == "bfs-cap0" else 8):
            raise ValueError("cap0 and positive BFS bounds differ")
        if self.kind == "scale24" and (
            self.dataset.name,
            self.dataset.source_vertex,
            self.dataset.expected_vertices,
            self.dataset.expected_edges,
        ) != ("generated-graph500-scale24", 13507776, 16777216, 268435456):
            raise ValueError("generated historical graph envelope differs")
        if self.kind != "scale24" and (
            self.dataset.name,
            self.dataset.expected_vertices,
            self.dataset.expected_edges,
            self.dataset.source_vertex,
        ) != ("signed-tiny", 13, 14, -5):
            raise ValueError("controls must precede the large graph")
        required = (
            {"tiny", "bfs-cap0", "host-pool-refusal"}
            if self.kind == "scale24"
            else set()
        )
        if {p.kind for p in self.prior_controls} != required or len(
            self.prior_controls
        ) != len(required):
            raise ValueError(
                "large case needs exactly three actual prior control qualifications"
            )
        return self


class Request(Model):
    version: Literal[1] = 1
    role: Literal["inspect", "driver", "worker", "client"]
    target: Target
    root: Path
    argv: list[str]
    environment: dict[str, str]
    timeout_seconds: int = Field(ge=30, le=21600)
    lease_seconds: Literal[15] = 15
    worker_id: Literal[1, 2] | None = None

    @field_validator("version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("exact integer protocol version required")
        return value

    @model_validator(mode="after")
    def ownership(self) -> Request:
        if (
            not self.root.is_absolute()
            or ".." in self.root.parts
            or self.root == self.target.repo
            or self.target.repo in self.root.parents
        ):
            raise ValueError(
                "fresh physical evidence namespace outside source required"
            )
        if (
            self.target.environment_file == self.root
            or self.root in self.target.environment_file.parents
        ):
            raise ValueError("secret file must remain outside owned evidence roots")
        if self.role == "worker" and (self.worker_id, self.target.name) not in (
            (1, "morrobay"),
            (2, "capitola"),
        ):
            raise ValueError("actual worker identity/physical host mapping required")
        return self


class ProcessProof(Model):
    pid: int
    pgid: int
    argv: list[str]
    started_utc: str
    finished_utc: str | None = None
    returncode: int | None = None
    wait_completed: bool = False
    group_absent: bool = False
    sigint_shutdown: bool = False
    forced_cleanup: bool = False


class RemoteReceipt(Model):
    outcome: Literal[
        "running",
        "completed_closed_supervised_process",
        "passed_native_host_inspection",
        "error",
    ] = "running"
    observed_utc: str
    supervisor_pid: int
    request: Request
    host: str
    architecture: str
    host_architecture: str | None = None
    translated: bool | None = None
    source_before: dict[str, str] = Field(default_factory=dict)
    source_after: dict[str, str] = Field(default_factory=dict)
    pins_before: list[Pin] = Field(default_factory=list)
    pins_after: list[Pin] = Field(default_factory=list)
    native_inspection: dict[str, JsonValue] = Field(default_factory=dict)
    inspection_steps: list[ProcessProof] = Field(default_factory=list)
    retained_files: dict[str, Pin] = Field(default_factory=dict)
    process: ProcessProof | None = None
    errors: list[str] = Field(default_factory=list)


class ActionReceipt(Model):
    outcome: Literal[
        "running",
        "completed_unqualified_bfs_export",
        "completed_expected_error_unqualified",
        "error",
    ] = "running"
    observed_utc: str
    plan: Plan
    pid: int
    workers: list[dict[str, JsonValue]] = Field(default_factory=list)
    stages: list[dict[str, JsonValue]] = Field(default_factory=list)
    native_request: dict[str, JsonValue] = Field(default_factory=dict)
    levels: int | None = None
    reached: int | None = None
    converged: bool | None = None
    export_projection: list[str] = Field(default_factory=list)
    output_uri: str | None = None
    client_error: str | None = None
    client_error_before_teardown: bool = False
    failure_details: dict[str, JsonValue] = Field(default_factory=dict)
    session_closed: bool = False
    errors: list[str] = Field(default_factory=list)


class SupervisorProof(Model):
    role: str
    host: str
    root: Path
    process: ProcessProof
    receipt: Pin | None = None
    fetched: dict[str, Pin] = Field(default_factory=dict)


class TypedControlQualification(Model):
    outcome: Literal[
        "passed_typed_bfs_cap_control", "passed_typed_host_pool_refusal_control"
    ]
    producer: Pin
    source: Literal["4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"]
    task_cause: Literal["bfs_level_cap", "allocation_refused"]
    both_physical_workers_executed: Literal[True]
    task_bound_cause_before_teardown: Literal[True]
    client_error_before_teardown: Literal[True]
    witnessed_process_closure: Literal[True]
    witnesses: list[Pin] = Field(min_length=1)
    historical_cause_identified: Literal[False] = False
    errors: list[str]


class NativeWorker(Model):
    worker_id: Literal[1, 2]
    pid: int = Field(gt=1)
    successful_native_tasks: int = Field(ge=0)


class OwnerReceipt(Model):
    outcome: Literal[
        "running", "completed_unqualified_closed_twohost_case", "error"
    ] = "running"
    observed_utc: str
    pid: int
    configuration: Pin
    plan: Plan
    supervisors: list[SupervisorProof] = Field(default_factory=list)
    transfers: list[ProcessProof] = Field(default_factory=list)
    host_receipts: list[RemoteReceipt] = Field(default_factory=list)
    action_receipt: ActionReceipt | None = None
    native_execution_workers: list[NativeWorker] = Field(default_factory=list)
    native_execution_job_id: int | None = None
    native_execution_session_id: str | None = None
    native_execution_witness_passed: bool = False
    immutable_closure: bool = False
    all_recorded_owned_processes_absent: bool = False
    locks_released: bool = False
    full_physical_output_qualified: Literal[False] = False
    historical_cause_identified: Literal[False] = False
    errors: list[str] = Field(default_factory=list)


class WorkerConfiguration(Model):
    plan: Plan
    common_environment: dict[str, str]


class Snapshot(Model):
    observed_utc: str
    recording: RemoteReceipt
    receipt: Pin
    source: dict[str, str]
    pins: list[Pin]
    processes_remaining: list[list[int]]
    all_recorded_processes_absent: bool
