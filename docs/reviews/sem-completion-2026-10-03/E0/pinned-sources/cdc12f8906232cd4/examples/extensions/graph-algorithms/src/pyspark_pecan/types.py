"""Typed records and validated option sets for Pecan.

Pydantic models validate *arguments* (ranges, literals, domains) once at the
call boundary. Graph *inputs* are not validated: Pecan assumes a valid graph
(see README, "Valid graph contract") and issues no jobs to check it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MASK: int = (1 << 64) - 1
INT64_MIN: int = -(1 << 63)
INT64_MAX: int = (1 << 63) - 1

EventKind = Literal["iteration_start", "iteration_end", "certificate"]
Direction = Literal["push", "pull"]
PageRankMethod = Literal["power", "delta", "pregel", "pregel_delta"]
WccMethod = Literal["min_label", "randomized", "randomized_fused"]
TraversalMethod = Literal["reference", "frontier", "push_pull", "delta_star", "pregel"]
Int64Id = Annotated[int, Field(ge=INT64_MIN, le=INT64_MAX)]


class IterationEvent(BaseModel):
    """One observer event. Metric fields are set only when the algorithm reports them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind
    algorithm: str
    iteration: int = Field(ge=0)
    run_path: str
    plan: str | None = None
    # traversal
    active_vertices: int | None = None
    direction: Direction | None = None
    frontier_edges: int | None = None
    discovered: int | None = None
    pull_early_exit: bool | None = None
    bucket: float | None = None
    # randomized contraction
    edges_before: int | None = None
    edges_after: int | None = None
    coefficient_a: int | None = None
    coefficient_b: int | None = None
    # delta PageRank (frontier_size also reports pregel_delta's active vertices)
    residual: float | None = None
    error_bound: float | None = None
    frontier_size: int | None = None
    active_edges: int | None = None
    reactivated_vertices: int | None = None
    normalized_residual_bound: float | None = None
    activation_threshold: float | None = None
    activation_mass: float | None = None

    def as_dict(self) -> dict[str, object]:
        """The event without unset metrics; the shape receipts and tests use."""
        return self.model_dump(exclude_none=True)


class ContractionStep(BaseModel):
    """One randomized contraction round."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    active_vertices: int | None = Field(default=None, ge=0)
    edges_before: int = Field(ge=0)
    edges_after: int = Field(ge=0)
    coefficient_a: int
    coefficient_b: int


class GraphOptions(BaseModel):
    """Controller settings validated once when the graph client is created."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    record_plans: bool = False
    repartition_checkpoints: bool = True
    snapshot_inputs: bool = True


class PageRankOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    reset_probability: float = Field(default=0.15, gt=0.0, le=1.0, allow_inf_nan=False)
    max_iterations: int = Field(default=20, ge=1)
    tolerance: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    partitions: int = Field(default=4, ge=1)
    method: PageRankMethod = "power"
    normalize: bool = False
    vote_to_halt: bool = False


class WccOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    max_iterations: int = Field(default=100, ge=1)
    partitions: int = Field(default=4, ge=1)
    method: WccMethod = "min_label"
    seed: int = Field(default=42, ge=0, le=MASK)
    canonical_labels: bool = True


class TraversalOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source: int = Field(ge=INT64_MIN, le=INT64_MAX)
    method: TraversalMethod = "frontier"
    directed: bool = True
    max_iterations: int = Field(default=1000, ge=1)
    partitions: int = Field(default=4, ge=1)
    delta: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)


class PregelSsspOptions(BaseModel):
    """Distance-only weighted Pregel, with an optional fixed superstep budget."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source: Int64Id
    directed: bool = True
    max_iterations: int = Field(default=1000, ge=1)
    partitions: int = Field(default=4, ge=1)
    vote_to_halt: bool = True


class ShortestPathsOptions(BaseModel):
    """Per-landmark unweighted hops; landmark membership is a caller contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    landmarks: tuple[Int64Id, ...] = Field(min_length=1)
    to_landmarks: bool = False
    max_iterations: int = Field(default=1000, ge=0)
    partitions: int = Field(default=4, ge=1)
    vote_to_halt: bool = True


class MassResidual(BaseModel):
    """Scalar statistics of a delta PageRank state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mass: float
    residual: float
