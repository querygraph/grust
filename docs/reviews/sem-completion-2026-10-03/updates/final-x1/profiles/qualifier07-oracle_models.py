"""Full undirected BFS certificate contracts; producer closure is a separate proof."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SOURCE: Literal["4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"] = (
    "4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"
)
PROJECTED = ("id", "distance", "hops", "parent")
NATIVE = (
    *PROJECTED,
    "owner",
    "worker_id",
    "pid",
    "adjacency_id",
    "incoming_adjacency_id",
    "phase",
    "levels",
    "reached",
    "converged",
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Identity(Model):
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")


class Pin(Identity):
    path: Path


class ResultSet(Model):
    directory: Path
    files: dict[str, Identity]

    @model_validator(mode="after")
    def paths(self) -> "ResultSet":
        if not self.directory.is_absolute() or ".." in self.directory.parts:
            raise ValueError("absolute result directory required")
        if not self.files or any(
            not name or Path(name).is_absolute() or ".." in Path(name).parts
            for name in self.files
        ):
            raise ValueError("nonempty safe complete raw inventory required")
        return self


class SourceContract(Model):
    repo: Path
    head: Literal["4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb"]
    tree: str = Field(pattern="^[a-f0-9]{40}$")
    files: list[Pin] = Field(min_length=1)


class Limits(Model):
    batch_rows: int = Field(default=65536, ge=1, le=262144)
    work_seconds: int = Field(default=7200, ge=1, le=43200)
    audit_seconds: int = Field(default=3600, ge=1, le=43200)


class Config(Model):
    dataset: Literal["graph500-generated-scale24", "tiny"]
    vertices: list[Pin] = Field(min_length=1)
    edges: list[Pin] = Field(min_length=1)
    result: ResultSet
    expected_vertices: int = Field(ge=1, le=20000000)
    expected_edges: int = Field(ge=0, le=300000000)
    source_id: int = Field(ge=-(2**63), le=2**63 - 1)
    max_levels: int = Field(ge=0, le=62)
    partitions: int = Field(ge=1, le=128)
    edge_source: Literal["src", "source"] = "src"
    edge_target: Literal["dst", "target"] = "dst"
    edge_schema_profile: Literal["endpoints2", "original_weight3"] = "endpoints2"
    undirected: Literal[True] = True
    method: Literal["reference"] = "reference"
    schema_profile: Literal["native13", "projected4"] = "native13"
    projected_terminal_receipt: Pin | None = None
    source_contract: SourceContract
    client_files: list[Pin] = Field(min_length=1)
    producer_evidence: list[Pin] = Field(min_length=1)
    helpers: dict[str, Pin]
    output: Path
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode="after")
    def contract(self) -> "Config":
        if self.dataset == "graph500-generated-scale24" and (
            self.expected_vertices,
            self.expected_edges,
            self.source_id,
            self.max_levels,
        ) != (16777216, 268435456, 13507776, 8):
            raise ValueError("original generated Graph500 contract differs")
        if (self.edge_source, self.edge_target) not in {
            ("src", "dst"),
            ("source", "target"),
        }:
            raise ValueError("explicit paired edge columns required")
        if self.edge_schema_profile == "original_weight3" and (
            self.edge_source,
            self.edge_target,
        ) != ("src", "dst"):
            raise ValueError("original three-field profile requires src/dst")
        if (
            self.dataset == "graph500-generated-scale24"
            and self.edge_schema_profile != "original_weight3"
        ):
            raise ValueError(
                "original generated files require the retained weight profile"
            )
        if (self.schema_profile == "projected4") != (
            self.projected_terminal_receipt is not None
        ):
            raise ValueError(
                "projected output requires pinned actual attribute receipt"
            )
        if set(self.helpers) != {
            "bfs_models.py",
            "bfs_io.py",
            "bfs_certificate.py",
            "bfs_oracle.py",
        }:
            raise ValueError("complete oracle helper set required")
        paths = [
            self.output,
            self.source_contract.repo,
            *(pin.path for pin in self.all_pins()),
        ]
        if any(not path.is_absolute() or ".." in path.parts for path in paths):
            raise ValueError("absolute scoped paths required")
        roots = [self.result.directory, self.source_contract.repo]
        if any(self.output == root or root in self.output.parents for root in roots):
            raise ValueError(
                "oracle evidence output must be separate from inputs/source"
            )
        return self

    def all_pins(self) -> list[Pin]:
        return [
            *self.vertices,
            *self.edges,
            *self.source_contract.files,
            *self.client_files,
            *self.producer_evidence,
            *self.helpers.values(),
            *(
                [self.projected_terminal_receipt]
                if self.projected_terminal_receipt is not None
                else []
            ),
        ]


class Terminal(Model):
    levels: int
    reached: int
    phase: int
    converged: int


class ProjectedTerminal(Model):
    outcome: Literal["observed_materialized_argentea_bfs_attributes"]
    source_id: int
    max_levels: int
    partitions: int
    result: ResultSet
    producer: Pin
    terminal: Terminal


class SourceObservation(Model):
    head: str
    tree: str
    detached: bool
    status: str


class PhysicalFile(Model):
    name: str
    fields: list[str]
    types: list[str]
    nullable: list[bool]
    footer_rows: int
    rows_examined: int = 0


class InputEdgeFile(PhysicalFile):
    input: Pin
    schema_profile: Literal["endpoints2", "original_weight3"]
    examined_columns: list[str]
    deliberately_unused_columns: list[str]


class Owner(Model):
    owner: int
    worker_id: int
    pid: int
    adjacency_id: int
    rows: int = 0


class Failures(Model):
    duplicate_rows: int = 0
    unknown_ids: int = 0
    null_ids: int = 0
    missing_ids: int = 0
    null_tuple: int = 0
    invalid_distance: int = 0
    distance_hops: int = 0
    source_tuple: int = 0
    non_source_zero: int = 0
    raw_diagnostics: int = 0
    owner_identity: int = 0
    minimum_parent: int = 0
    edge_level_gap: int = 0
    edge_reachability_closure: int = 0

    def total(self) -> int:
        return sum(int(value) for value in self.model_dump().values())


class Receipt(Model):
    outcome: Literal[
        "checking",
        "passed_full_undirected_BFS_certificate",
        "mismatch",
        "partial_output",
        "cap_unqualified",
        "error",
    ] = "checking"
    started_utc: str
    finished_utc: str | None = None
    configuration: Pin
    source_before: SourceObservation | None = None
    source_after: SourceObservation | None = None
    pins_before: list[Pin] = Field(default_factory=list)
    pins_after: list[Pin] = Field(default_factory=list)
    raw_files_before: dict[str, Identity] = Field(default_factory=dict)
    raw_files_after: dict[str, Identity] = Field(default_factory=dict)
    physical_files: list[PhysicalFile] = Field(default_factory=list)
    input_edge_physical_files: list[InputEdgeFile] = Field(default_factory=list)
    vertex_rows: int = 0
    edge_rows: int = 0
    output_rows: int = 0
    unique_output_ids: int = 0
    reached: int = 0
    max_distance: int = -1
    computed_terminal_levels: int | None = None
    observed_terminal: Terminal | None = None
    owners: list[Owner] = Field(default_factory=list)
    failures: Failures = Field(default_factory=Failures)
    full_domain_passed: bool = False
    all_original_edges_examined: bool = False
    parent_paths_and_minimum_parent_passed: bool = False
    all_edge_lower_bound_and_reachability_passed: bool = False
    terminal_empty_expansion_cap_passed: bool = False
    full_physical_certificate_passed: bool = False
    own_identity_closure_passed: bool = False
    full_array_bytes: int = 0
    identity_domain_verified: bool = False
    declared_batch_array_allowance_bytes: int = 0
    array_memory_scope: str = "full_array_bytes sums six retained ndarray.nbytes (34V); batch allowance is advisory 512*batch_rows, not a proved allocator/decoder/physical peak. Internal sorting/Arrow buffers, metadata, interpreter and runtime headroom are not bounded here; root must observe RSS separately."
    progress: str = "initial"
    errors: list[str] = Field(default_factory=list)
    certain_producer_process_closure: Literal[False] = False
    native_ABI_or_historical_cause_qualified: Literal[False] = False
    scope: str = "All original undirected edges plus source-rooted decreasing parent paths prove exact BFS distances and minimum signed-ID preceding-level parents. Outside algorithm timer; no CSR/queue replay, process closure, allocator or historical fault claim."
