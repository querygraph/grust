"""The materialized Arrow bridge's configuration and unvalidated receipts."""

from pathlib import Path
from typing import Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

EXTENSION_SOURCE: Final = "4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"
NATIVE_RUNTIME: Final = "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Plan(Record):
    dataset: Literal["cit-Patents", "graph500-24", "tiny"]
    vertices: Path
    edges: Path
    vertex_id_column: str = Field(default="id", min_length=1)
    edge_source_column: str = Field(default="source", min_length=1)
    edge_target_column: str = Field(default="target", min_length=1)
    output_root: Path
    receipt: Path
    ids: Literal["int64"]
    calls: Literal[1, 3]
    workers: Literal[16] = 16
    binary: Path
    venv: Path
    python_home: Path
    python_purelib: Path
    python_library_directory: Path
    sail_pool_bytes: Literal[32212254720] = 32212254720
    native_quota_bytes: Literal[23622320128] = 23622320128
    timeout_seconds: Literal[1800] = 1800
    chunk_rows: int = Field(default=262144, ge=2, le=262144)
    extension_source_commit: Literal["4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"] = (
        EXTENSION_SOURCE
    )
    native_runtime_commit: Literal["9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"] = (
        NATIVE_RUNTIME
    )

    @field_validator("calls", mode="before")
    @classmethod
    def calls_are_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("call count must be an integer, never a boolean")
        return value

    @model_validator(mode="after")
    def paths(self) -> Self:
        paths = (
            self.vertices,
            self.edges,
            self.output_root,
            self.receipt,
            self.binary,
            self.venv,
            self.python_home,
            self.python_purelib,
            self.python_library_directory,
        )
        if any(not path.is_absolute() or ".." in path.parts for path in paths):
            raise ValueError("all paths must be absolute without parent traversal")
        if self.vertices == self.edges:
            raise ValueError("vertices and edges must be separate originals")
        for path in paths:
            if path != self.output_root and path.is_relative_to(self.output_root):
                raise ValueError("fresh output root must not contain configured inputs")
        if not self.python_purelib.is_relative_to(self.venv):
            raise ValueError("Python purelib must belong to the declared new venv")
        if self.dataset != "tiny" and self.chunk_rows != 262144:
            raise ValueError("main bridge conditions require 262144-row chunks")
        return self


class FilePin(Record):
    path: Path
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Span(Record):
    started_ns: int = Field(ge=0)
    ended_ns: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.ended_ns < self.started_ns:
            raise ValueError("monotonic span ends before it starts")
        return self

    @property
    def seconds(self) -> float:
        return (self.ended_ns - self.started_ns) / 1_000_000_000


class Phase(Record):
    name: Literal[
        "read_parquet", "csr_and_graph", "algorithm_materialize", "write_parquet"
    ]
    call: int | None = Field(default=None, ge=1, le=3)
    span: Span
    completed: bool


class OutputAttempt(Record):
    call: int = Field(ge=1, le=3)
    path: Path
    completed: bool = False


class ProjectionBuild(Record):
    key: str
    seconds: float = Field(ge=0)
    live_bytes_before: int = Field(ge=0)
    admitted_bytes: int = Field(ge=0)


class GraphCache(Record):
    name: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    revision: int = Field(ge=1)
    projections: int = Field(ge=0)
    staged_bytes: int = Field(ge=0)
    projection_builds: list[ProjectionBuild]


class NativeMemory(Record):
    limit_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    peak_bytes: int = Field(ge=0)
    staged_bytes: int = Field(ge=0)


class NativeStatus(Record):
    memory: NativeMemory
    graphs: list[GraphCache]
    reads: list[JsonValue]

    def one_cached_projection(self) -> bool:
        return (
            len(self.graphs) == 1
            and self.graphs[0].name == "g"
            and self.graphs[0].projections == 1
            and len(self.graphs[0].projection_builds) == 1
        )


class ServerExit(Record):
    pid: int = Field(gt=0)
    pgid: int = Field(gt=0)
    argv: list[str]
    launched_utc: str
    closed_utc: str | None = None
    returncode: int | None = None
    wait_completed: bool = False
    termination_requested: bool = False
    forced_kill: bool = False
    scope: str = "Direct owned native server was waited; group closure is parent-owned."


class Error(Record):
    phase: str
    detail: str


class ExclusiveSemPhases(Record):
    read_seconds: float | None = Field(default=None, ge=0)
    csr_and_graph_build_seconds: float | None = Field(default=None, ge=0)
    algorithm_seconds: float | None = Field(default=None, ge=0)
    write_seconds: float | None = Field(default=None, ge=0)
    availability: Literal[
        "unavailable_failed_pipeline", "observed_materialized_arrow_bridge"
    ] = "unavailable_failed_pipeline"
    reason: str = (
        "Separate materialized bridge phases: client Parquet-to-Arrow read; bounded "
        "bounded inline Arrow IPC/checkpoint jobs plus stage/projectionStats; all WCC kernels and "
        "full Arrow result transport; all client Parquet writes. Not native CSR-only "
        "or kernel-only clocks and not the prior native-Parquet profile."
    )


class ArrowHandoff(Record):
    input_name: Literal["vertices", "edges"]
    rows: int = Field(ge=0)
    chunk_rows: int = Field(ge=2, le=262144)
    chunks: int = Field(ge=1)
    checked_ipc_encodings: int = Field(default=0, ge=0)
    create_dataframe_calls: int = Field(default=0, ge=0)
    checkpoint_attempts: int = Field(default=0, ge=0)
    checkpoints_completed: int = Field(default=0, ge=0)
    cached_chunks: int = Field(ge=0)
    remote_reference_ids: list[str] = Field(default_factory=list)
    maximum_ipc_bytes: int = Field(ge=0, le=33554432)
    encoded_ipc_bytes: int = Field(ge=0)
    balanced_union_depth: int = Field(ge=0)
    cache_threshold_bytes: Literal[67108864] = 67108864
    eager_checkpoints: Literal[True] = True
    checkpoint_sort_applied: Literal[False] = False
    completed: bool = False


class Receipt(Record):
    execution_profile: Literal["chunk_checkpoint_arrow_client_four_phase"] = (
        "chunk_checkpoint_arrow_client_four_phase"
    )
    observed_utc: str
    started_utc: str
    outcome: Literal["running", "completed_unvalidated", "failed", "timeout"]
    configuration: Plan
    configuration_pin: FilePin
    worker_source: FilePin
    models_source: FilePin
    owner_pid: int = Field(gt=0)
    python_version: str
    pyspark_version: str
    client_plan_source: FilePin
    client_session_source: FilePin
    client_dataframe_source: FilePin
    python_executable: Path
    environment: dict[str, str]
    server: ServerExit | None = None
    pipeline: Span | None = None
    pipeline_seconds: float | None = Field(default=None, ge=0)
    pipeline_completed: bool = False
    phases: list[Phase] = Field(default_factory=list)
    outputs: list[OutputAttempt] = Field(default_factory=list)
    output_projection: list[Literal["id", "component"]] = ["id", "component"]
    stage_receipt: JsonValue | None = None
    projection_receipt: JsonValue | None = None
    native_status: JsonValue | None = None
    projection_reused: bool | None = None
    arrow_handoffs: list[ArrowHandoff] = Field(default_factory=list)
    exclusive_sem_phases: ExclusiveSemPhases = Field(default_factory=ExclusiveSemPhases)
    graph_dropped: bool = False
    spark_stopped: bool = False
    errors: list[Error] = Field(default_factory=list)
    scope: str = (
        "One unvalidated native WCC series on a shared host. Main continuous "
        "clock starts before materialized client input read and ends at the last "
        "full client Parquet write. Chunk IPC encoding and unsorted eager checkpoint "
        "jobs are in "
        "CSR/graph; result transport is in algorithm. All full inputs/results "
        "remain client-resident during their phases. Software pools are not an OS cap. "
        "Session setup, post-pipeline diagnostics, all validation, graph/session "
        "teardown and native process exit are outside that clock. Parent supplies "
        "source/input admission, physical output oracles and full process closure."
    )
