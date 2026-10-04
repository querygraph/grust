"""Bucketed all-edge stepping (delta-star), with a bounded client controller.

Unlike classical light/heavy delta-stepping, every selected vertex relaxes all
outgoing edges. Pending vertices stay server-side. Bucket closure occurs by
reselecting the minimum pending bucket until it is empty. This is deliberately
named delta_star, not classical delta-stepping or Dijkstra.

Distances are assumed to stay finite and `distance / delta` is assumed to fit
the engine's floor (the valid graph contract); no job checks either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F

from ._contracts import ConvergenceError, first_row
from .traversal_state import initial_state

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import GraphResult
    from .staging import StagingRun


def execute(graph: GraphAlgorithms, run: StagingRun, vertices: DataFrame, adjacency: DataFrame, size: int | None,
            source: int, delta: float, limit: int) -> GraphResult:
    path, state = run.materialize(initial_state(run.spark, source))
    pending_path, pending = path, state
    for step in range(1, limit + 1):
        run.cancellation.check()
        bucket: float | None = first_row(pending.agg(F.min(F.floor(F.col("distance") / delta))))[0]
        if bucket is None:
            result_path, result = run.materialize(vertices.join(state, "id", "left"))
            return run.finish(result_path, result, algorithm="sssp-delta-star", iterations=step - 1,
                              converged=True)
        active = pending.where(F.floor(F.col("distance") / delta) == bucket)
        # Frontier on the left: the partitioned hash join builds on its left input.
        candidates = active.join(adjacency, active.id == adjacency.src).select(
            adjacency.dst.alias("id"), (active.distance + adjacency.weight).alias("distance"),
            (active.hops + 1).alias("hops"), active.id.alias("parent"))
        relaxed = state.unionByName(candidates).groupBy("id").agg(
            F.min(F.struct("distance", "hops", "parent")).alias("best")).select("id", "best.*")
        graph._observe(run, "sssp-delta-star", step, "iteration_start", bucket=float(bucket), plan_of=relaxed)
        next_path, updated = run.materialize(relaxed)
        before = state.select("id", F.struct("distance", "hops", "parent").alias("before"))
        # A null `before` is a newly reached vertex, not an invalid row.
        changed = updated.join(before, "id", "left").where(
            F.col("before").isNull() | (F.struct("distance", "hops", "parent") != F.col("before"))
        ).select("id", "distance", "hops", "parent")
        # Remove processed and superseded records before adding improved labels.
        remaining = pending.join(active.select("id"), "id", "left_anti").join(
            changed.select("id"), "id", "left_anti")
        next_pending_path, next_pending = run.materialize(remaining.unionByName(changed))
        for obsolete in {path, pending_path}:
            run.remove(obsolete)
        path, state = next_path, updated
        pending_path, pending = next_pending_path, next_pending
        graph._observe(run, "sssp-delta-star", step, "iteration_end", bucket=float(bucket))
    # Certify completion even when the last allowed expansion emptied the queue.
    if pending.limit(1).count():
        raise ConvergenceError(f"sssp-delta-star did not converge in {limit} iterations")
    result_path, result = run.materialize(vertices.join(state, "id", "left"))
    return run.finish(result_path, result, algorithm="sssp-delta-star", iterations=limit, converged=True)
