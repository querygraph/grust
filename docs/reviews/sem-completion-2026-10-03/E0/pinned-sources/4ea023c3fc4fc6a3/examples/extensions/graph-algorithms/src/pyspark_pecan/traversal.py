"""Table-based single-source traversal with bounded client-side reductions.

The source is assumed to be a vertex; weights are assumed finite and
non-negative with finite path sums (the valid graph contract). No job checks
either; a violation produces an undefined result, not an error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F
from pyspark.sql.types import DoubleType

from . import traversal_bfs, traversal_stepping
from ._contracts import ConvergenceError
from .traversal_state import initial_state

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun
    from .types import TraversalOptions


def execute(graph: GraphAlgorithms, vertices: DataFrame, edges: DataFrame, *, options: TraversalOptions,
            weighted: bool, cancellation: CancellationToken | None) -> GraphResult:
    if weighted and ("weight" not in edges.columns or
                     not isinstance(edges.schema["weight"].dataType, DoubleType)):
        raise ValueError("SSSP requires a DOUBLE weight column")
    algorithm = ("sssp" if weighted else "bfs") + "-" + options.method
    source = options.source
    method = options.method

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        if options.directed:
            # The input (its snapshot, or the caller's stable frame) already is
            # the adjacency; writing it again would only copy every edge.
            adjacency = edges
        else:
            _, adjacency = run.materialize(edges.unionByName(edges.select(
                F.col("dst").alias("src"), F.col("src").alias("dst"), *edges.columns[2:])))
        # An unweighted edge costs one hop; no weight column is stored for it.
        weight = adjacency.weight if weighted else F.lit(1.0)
        if method == "push_pull":
            assert size is not None
            return traversal_bfs.execute(graph, run, vertices, adjacency, size, source, options.max_iterations)
        if method == "delta_star":
            return traversal_stepping.execute(graph, run, vertices, adjacency, size, source, options.delta,
                            options.max_iterations)
        path, reached = run.materialize(initial_state(run.spark, source))
        frontier_path, frontier = path, reached
        for step in range(1, options.max_iterations + 1):
            run.cancellation.check()
            active = reached if method == "reference" else frontier
            # The frontier is the left input on purpose: in cluster mode the expansion is
            # a partitioned hash join whose build side is the left input, so the small
            # side must be written first or every worker builds a table over its share of
            # the adjacency (the recorded plans of the 2026-09-29 capacity cells).
            candidates = active.join(adjacency, active.id == adjacency.src).select(
                adjacency.dst.alias("id"),
                (active.distance + weight).alias("distance"),
                (active.hops + 1).alias("hops"), active.id.alias("parent"))
            # Lexicographic minimization makes parent choice deterministic and
            # gives every parent a strictly smaller hop count, even at weight 0.
            updated = reached.unionByName(candidates).groupBy("id").agg(
                F.min(F.struct("distance", "hops", "parent")).alias("best")
            ).select("id", "best.*")
            graph._observe(run, algorithm, step, "iteration_start", plan_of=updated)
            next_path, next_reached = run.materialize(updated)
            before = reached.select("id", F.struct("distance", "hops", "parent").alias("before"))
            # A null `before` is a newly reached vertex, not an invalid row.
            changed = next_reached.join(before, "id", "left").where(
                F.col("before").isNull() |
                (F.struct("distance", "hops", "parent") != F.col("before"))
            ).select("id", "distance", "hops", "parent")
            change_path, next_frontier = run.materialize(changed)
            count: int = next_frontier.count()
            for obsolete in {path, frontier_path}:
                run.remove(obsolete)
            path, reached = next_path, next_reached
            frontier_path, frontier = change_path, next_frontier
            graph._observe(run, algorithm, step, "iteration_end", active_vertices=count)
            if not count:
                result_path, result = run.materialize(vertices.join(reached, "id", "left"))
                return run.finish(result_path, result, algorithm=algorithm,
                                  iterations=step, converged=True)
        raise ConvergenceError(f"{algorithm} did not converge in {options.max_iterations} iterations")

    return graph._run(vertices, edges, options.partitions, cancellation, body,
                      edge_columns=("src", "dst", "weight") if weighted else ("src", "dst"),
                      count_vertices=method == "push_pull")
