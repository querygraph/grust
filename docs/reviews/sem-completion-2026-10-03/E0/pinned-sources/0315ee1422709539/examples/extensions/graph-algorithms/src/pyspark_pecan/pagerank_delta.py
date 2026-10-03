"""Signed-residual PageRank with an active frontier and a global certificate.

For d=1-reset and the column-stochastic transition P (uniform dangling
columns), maintain r = reset/N + d*P*x - x. Push a subset a of r:
x <- x+a; r <- r-a+d*P*a. Inactive residual is retained, not discarded.
Use threshold min(||r||_1/(2*N), tolerance*sum(x)/(4*N)). The tolerance-scaled
term retains insignificant tail corrections while larger corrections propagate;
the relative cap leaves at most half the pending norm inactive, so that norm
contracts by at least 1-reset/2 in exact arithmetic. Activity can shrink and
grow; vertices can reactivate after receiving later messages.

For m=sum(x), the residual of normalized x/m is bounded by 2*||r||_1/m.
This bound triggers a full recomputation, never substitutes for the final
certificate: ||reset/N+d*P*y-y||_1 <= tolerance. Consequently the normalized
output's L1 distance from stationary PageRank is at most tolerance/reset.
All arithmetic uses DOUBLE; distributed sums are not promised bitwise stable.

Only active sources emit edge messages. A relational join may still scan the
Parquet edge table; this client does not claim indexed adjacency or fewer
physical edge reads. Scalar frontier counts report propagated edge messages.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from pyspark.sql.connect import functions as F

from ._contracts import ConvergenceError, first_row
from .types import EventKind, MassResidual

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun
    from .types import PageRankOptions


def _statistics(run: StagingRun, state: DataFrame) -> MassResidual:
    """Mass and residual of a state; the scalars are checked for finiteness (no extra job)."""
    run.cancellation.check()
    row = state.agg(
        F.sum("pagerank").alias("mass"),
        F.min("pagerank").alias("minimum"),
        F.sum(F.abs(F.col("pending"))).alias("residual"),
    ).first()
    assert row is not None
    run.cancellation.check()
    mass: float = row["mass"]
    residual: float = row["residual"]
    minimum: float = row["minimum"]
    if (not math.isfinite(mass) or mass <= 0 or
            not math.isfinite(residual) or not math.isfinite(minimum) or minimum < 0):
        raise ArithmeticError("delta PageRank produced invalid floating-point state")
    return MassResidual(mass=mass, residual=residual)


def _incoming(edges: DataFrame, state: DataFrame, column: str) -> DataFrame:
    return edges.join(state, edges.src == state.id).select(
        edges.dst.alias("id"), (state[column] / state.degree).alias("message"),
    ).groupBy("id").agg(F.sum("message").alias("incoming"))


def _certificate(run: StagingRun, state: DataFrame, edges: DataFrame, size: int, damping: float,
                 reset: float, mass: float) -> tuple[str, DataFrame, MassResidual]:
    """Materialize normalized scores and a freshly recomputed true residual."""
    normalized = state.select(
        "id", "degree", (F.col("pagerank") / F.lit(mass)).alias("pagerank"),
        "ever_active", "active_previous",
    )
    run.cancellation.check()
    dangling: float = first_row(normalized.where(F.col("degree") == 0).agg(F.sum("pagerank")))[0] or 0.0
    run.cancellation.check()
    incoming = _incoming(edges, normalized, "pagerank")
    certified = normalized.join(incoming, "id", "left").select(
        "id", "degree", "pagerank", "ever_active", "active_previous",
        (F.lit(reset / size) + F.lit(damping) * (
            F.coalesce(F.col("incoming"), F.lit(0.0)) + F.lit(dangling / size)
        ) - F.col("pagerank")).alias("pending"),
    )
    path, certified = run.materialize(certified)
    return path, certified, _statistics(run, certified)


def _finish(run: StagingRun, state: DataFrame, steps: int, residual: float, reset: float) -> GraphResult:
    path, result = run.materialize(state.select("id", "pagerank"))
    handle = run.finish(path, result, algorithm="pagerank-delta", iterations=steps, converged=True)
    handle.method = "delta"
    handle.residual = residual
    handle.error_bound = residual / reset
    return handle


def execute(graph: GraphAlgorithms, vertices: DataFrame, edges: DataFrame, *, options: PageRankOptions,
            cancellation: CancellationToken | None) -> GraphResult:
    """Run frontier pushes; tolerance bounds the final global fixed-point L1 residual.

    Unlike fixed-K power iteration, delta execution requires a positive tolerance.
    max_iterations counts frontier pushes, excluding initialization and final
    certificates. A stationary uniform initialization therefore uses zero pushes.
    Failure to certify at the limit raises ConvergenceError and cleans the run.
    """
    if options.tolerance is None:
        raise ValueError("delta PageRank requires a positive tolerance")
    tolerance: float = options.tolerance
    reset = options.reset_probability
    damping = 1.0 - reset
    max_iterations = options.max_iterations

    def observe(run: StagingRun, step: int, kind: EventKind, **metrics: Any) -> None:
        graph._observe(run, "pagerank-delta", step, kind, **metrics)
        run.cancellation.check()

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        assert size is not None  # PageRank requests N for normalization.
        if not size:
            empty = vertices.withColumn("pagerank", F.lit(0.0))
            return _finish(run, empty, 0, 0.0, reset)
        degrees = edges.groupBy("src").count().select(
            F.col("src").alias("id"), F.col("count").alias("degree"),
        )
        path, state = run.materialize(vertices.join(degrees, "id", "left").select(
            "id", F.coalesce(F.col("degree"), F.lit(0)).alias("degree"),
            F.lit(1.0 / size).alias("pagerank"),
            F.lit(False).alias("ever_active"), F.lit(False).alias("active_previous"),
        ))
        next_path, state, stats = _certificate(run, state, edges, size, damping, reset, 1.0)
        run.remove(path)
        path = next_path
        observe(run, 0, "certificate", residual=stats.residual, error_bound=stats.residual / reset)
        if stats.residual <= tolerance:
            return _finish(run, state, 0, stats.residual, reset)

        for step in range(1, max_iterations + 1):
            observe(run, step, "iteration_start")
            activation_mass = stats.mass
            threshold = min(stats.residual / (2.0 * size), tolerance * activation_mass / (4.0 * size))
            active_path, active = run.materialize(state.where(
                F.abs(F.col("pending")) > F.lit(threshold),
            ).select("id", "degree", F.col("pending").alias("push"),
                     "ever_active", "active_previous"))
            run.cancellation.check()
            activity = active.agg(
                F.count("*").alias("vertices"), F.sum("degree").alias("edges"),
                F.sum(F.when(F.col("degree") == 0, F.col("push")).otherwise(0.0)).alias("dangling"),
                F.sum((F.col("ever_active") & ~F.col("active_previous")).cast("long")).alias("reactivated"),
            ).first()
            assert activity is not None
            run.cancellation.check()
            if activity.vertices == 0:
                raise ArithmeticError("positive PageRank residual produced an empty frontier")
            incoming = _incoming(edges, active, "push")
            selected = active.select("id", "push")
            next_state = state.join(selected, "id", "left").join(incoming, "id", "left")
            # A null `push` means the vertex was not in the frontier this step.
            push = F.coalesce(F.col("push"), F.lit(0.0))
            next_state = next_state.select(
                "id", "degree", (F.col("pagerank") + push).alias("pagerank"),
                (F.col("ever_active") | F.col("push").isNotNull()).alias("ever_active"),
                F.col("push").isNotNull().alias("active_previous"),
                (F.col("pending") - push + F.lit(damping) * (
                    F.coalesce(F.col("incoming"), F.lit(0.0)) + F.lit((activity.dangling or 0.0) / size)
                )).alias("pending"),
            )
            next_path, next_state = run.materialize(next_state)
            stats = _statistics(run, next_state)
            run.remove(active_path)
            run.remove(path)
            path, state = next_path, next_state
            bound = 2.0 * stats.residual / stats.mass
            observe(run, step, "iteration_end", frontier_size=activity.vertices,
                    active_edges=activity.edges or 0, reactivated_vertices=activity.reactivated or 0,
                    residual=stats.residual, normalized_residual_bound=bound,
                    activation_threshold=threshold, activation_mass=activation_mass)
            if bound <= tolerance or step == max_iterations:
                next_path, certified, stats = _certificate(run, state, edges, size, damping, reset, stats.mass)
                run.remove(path)
                path, state = next_path, certified
                observe(run, step, "certificate", residual=stats.residual, error_bound=stats.residual / reset)
                if stats.residual <= tolerance:
                    return _finish(run, state, step, stats.residual, reset)
                # A failed certificate rebases state to the normalized scores
                # and recomputed residual before any further frontier pushes.
        raise ConvergenceError(
            f"delta PageRank did not reach global residual tolerance in {max_iterations} iterations "
            f"(residual={stats.residual}, tolerance={tolerance})"
        )

    return graph._run(vertices, edges, options.partitions, cancellation, body)
