"""Delta PageRank as GraphX's dynamic vertex program, in the form of graphframes-rs.

The reference is GraphX `PageRank.runUntilConvergence` as graphframes-rs
implements it over its Pregel engine (`src/algorithm/centrality/pagerank.rs`).
A vertex carries its out-degree, its accumulated rank and the rank it gained
in the last step, its delta. Both start at the reset probability. In a step
every vertex whose delta exceeds the tolerance sends delta/out_degree along
its out-edges, and every vertex then sets

    delta    = (1 - reset) * (sum of received messages, 0 when none)
    pagerank = pagerank + delta

In the first step all vertices send. There is no dangling term, no residual
and no certificate. The program below is his, column for column, on the
Pregel loop of `pregel.py`; the state is the only relation a step writes,
so a step is one job. Ranks are on GraphX's scale, where a vertex starts at `reset` and
the tolerance compares to a single vertex's gain; `normalize=True` divides by
the total at the end, as graphframes-rs always does.

A fixed budget runs exactly `max_iterations` steps and never counts anything
(graphframes-rs with `max_iter > 0`). With `vote_to_halt` a step also counts
the vertices still above the tolerance and the run stops when there are none
(GraphX, and graphframes-rs with `max_iter = 0`); reaching the cap first
raises ConvergenceError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F

from ._contracts import ConvergenceError, first_row
from .pregel import Pregel, msg, src

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun
    from .types import PageRankOptions

ALGORITHM = "pagerank-pregel-delta"


def program(graph: GraphAlgorithms, options: PageRankOptions, tolerance: float) -> Pregel:
    """graphframes-rs's PageRank as a Pregel program over vertices that carry `degree`."""
    reset = options.reset_probability
    gained = F.lit(1.0 - reset) * F.coalesce(msg(), F.lit(0.0))
    pregel = (Pregel(graph, algorithm=ALGORITHM)
              .vertex_column("pagerank", F.lit(reset), F.col("pagerank") + gained)
              .vertex_column("delta", F.lit(reset), gained)
              .vertex_column("degree", F.col("degree"), F.col("degree"))
              .message(src("delta") / src("degree"), "src_to_dst")
              .aggregate(F.sum(msg()))
              # Participation prunes the senders every step; the vote only decides when to stop.
              .participation("participates", F.lit(True), gained > F.lit(tolerance))
              .skip_destination_state()
              .max_iterations(options.max_iterations))
    if options.vote_to_halt:
        pregel.vote_to_halt("active", gained > F.lit(tolerance))
    return pregel


def execute(graph: GraphAlgorithms, vertices: DataFrame, edges: DataFrame, *, options: PageRankOptions,
            cancellation: CancellationToken | None) -> GraphResult:
    if options.tolerance is None:
        raise ValueError("pregel_delta PageRank requires a positive tolerance")
    pregel = program(graph, options, options.tolerance)

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        degrees = edges.groupBy("src").count().select(F.col("src").alias("id"), F.col("count").alias("degree"))
        with_degree = vertices.join(degrees, "id", "left").select(
            "id", F.coalesce(F.col("degree"), F.lit(0)).alias("degree"))
        outcome = pregel.loop(run, with_degree, edges)
        if outcome.converged is False:
            raise ConvergenceError(
                f"pregel_delta PageRank still had active vertices after {options.max_iterations} iterations")
        state = outcome.state
        ranks = state.select("id", "pagerank")
        if options.normalize:
            run.cancellation.check()
            # The total is null for a graph without vertices; there is then nothing to divide.
            total: float | None = first_row(state.agg(F.sum("pagerank")))[0]
            if total:
                ranks = state.select("id", (F.col("pagerank") / F.lit(total)).alias("pagerank"))
        result_path, result = run.materialize(ranks)
        handle = run.finish(result_path, result, algorithm=ALGORITHM, iterations=outcome.iterations,
                            converged=outcome.converged)
        handle.method = options.method
        return handle

    return graph._run(vertices, edges, options.partitions, cancellation, body, count_vertices=False)
