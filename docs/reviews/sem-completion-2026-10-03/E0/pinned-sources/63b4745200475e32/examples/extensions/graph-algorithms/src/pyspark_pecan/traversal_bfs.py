"""Push/pull relational BFS; pull joins do not promise adjacency early exit."""

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


def execute(graph: GraphAlgorithms, run: StagingRun, vertices: DataFrame, adjacency: DataFrame, size: int,
            source: int, limit: int, alpha: float = 14.0, beta: float = 24.0) -> GraphResult:
    degrees = adjacency.groupBy("src").count().select(F.col("src").alias("id"), F.col("count").alias("degree"))
    _, degrees = run.materialize(degrees)
    path, reached = run.materialize(initial_state(run.spark, source))
    frontier_path, frontier = path, reached
    remaining: int = adjacency.count()
    pull = False
    just_left_pull = False
    for level in range(1, limit + 1):
        run.cancellation.check()
        volume: int = first_row(frontier.join(degrees, "id").agg(F.sum("degree")))[0] or 0
        remaining = max(0, remaining - volume)
        if not pull and not just_left_pull and volume > remaining / alpha:
            pull = True
        just_left_pull = False
        direction = "pull" if pull else "push"
        unvisited = vertices.join(reached.select("id"), "id", "left_anti")
        if pull:
            # Restrict destination rows before testing frontier membership.
            # Unlike native BFS, this ordinary relational plan cannot stop an
            # adjacency scan immediately on finding its first parent.
            # Smaller input on the left: the partitioned hash join builds on its left input.
            candidates = unvisited.join(adjacency, unvisited.id == adjacency.dst).select("src", "dst")
            candidates = candidates.join(frontier.select(F.col("id").alias("active")),
                                         F.col("src") == F.col("active"), "left_semi")
        else:
            candidates = frontier.join(adjacency, frontier.id == adjacency.src).select("src", "dst")
            candidates = candidates.join(unvisited, candidates.dst == unvisited.id, "left_semi")
        expansion = candidates.groupBy("dst").agg(F.min("src").alias("parent")).select(
            F.col("dst").alias("id"), F.lit(float(level)).alias("distance"),
            F.lit(level).cast("long").alias("hops"), "parent")
        graph._observe(run, "bfs-push-pull", level, "iteration_start", direction=direction,
                       frontier_edges=volume, plan_of=expansion)
        next_frontier_path, next_frontier = run.materialize(expansion)
        count: int = next_frontier.count()
        graph._observe(run, "bfs-push-pull", level, "iteration_end", direction=direction,
                       frontier_edges=volume, discovered=count, pull_early_exit=False)
        if not count:
            output_path, output = run.materialize(vertices.join(reached, "id", "left"))
            return run.finish(output_path, output, algorithm="bfs-push-pull", iterations=level, converged=True)
        next_path, next_reached = run.materialize(reached.unionByName(next_frontier))
        for obsolete in {path, frontier_path}:
            run.remove(obsolete)
        path, reached = next_path, next_reached
        frontier_path, frontier = next_frontier_path, next_frontier
        if pull and count < size / beta:
            pull = False
            just_left_pull = True
    raise ConvergenceError(f"bfs-push-pull did not converge in {limit} iterations")
