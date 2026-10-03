"""Shortest-distance programs on the common Pregel loop.

Weighted SSSP sends one DOUBLE distance and aggregates MIN. Landmark hops
follow graphframes-rs's `connectivity/shortest_paths.rs` at b4da56d: one INT
column and named MIN message per landmark, MAX_INT as unreachable, forward
edges by default, and reversed edges for distances to landmarks. Neither
program inspects graph validity. Only participating sources join adjacency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F
from pyspark.sql.types import DoubleType

from ._contracts import ConvergenceError
from .pregel import Pregel, edge, msg, src

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun
    from .types import PregelSsspOptions, ShortestPathsOptions

MAX_HOPS = (1 << 31) - 1


def sssp_program(graph: GraphAlgorithms, options: PregelSsspOptions) -> Pregel:
    """Nonnegative weighted SSSP, with source distance 0 and null unreachable."""
    changed = msg().isNotNull() & (F.col("distance").isNull() | (msg() < F.col("distance")))
    source = F.col("id") == F.lit(options.source)
    program = (
        Pregel(graph, algorithm="sssp-pregel")
        .vertex_column(
            "distance",
            F.when(source, F.lit(0.0)).otherwise(F.lit(None).cast("double")),
            F.least(F.col("distance"), msg()),
        )
        .participation("participates", source, changed)
        .edge_column("weight")
        .message(src("distance") + edge("weight"), "src_to_dst")
        .aggregate(F.min(msg()))
        .skip_destination_state()
        .max_iterations(options.max_iterations)
    )
    if options.vote_to_halt:
        program.vote_to_halt("active", changed)
    return program


def landmarks_program(graph: GraphAlgorithms, options: ShortestPathsOptions) -> Pregel:
    """graphframes-rs's per-landmark hop program, on the selected edge direction."""
    changed = F.lit(False)
    initial_participation = F.lit(False)
    program = Pregel(graph, algorithm="shortest-paths-pregel")
    for landmark in sorted(options.landmarks):
        name = str(landmark)
        column = "dist_" + name
        distance = F.col(column)
        received = msg(name)
        initial_participation = initial_participation | (F.col("id") == F.lit(landmark))
        changed = changed | (distance > received)
        sent = F.when(src(column) < F.lit(MAX_HOPS), src(column) + F.lit(1)).otherwise(F.lit(MAX_HOPS))
        program.vertex_column(
            column,
            F.when(F.col("id") == F.lit(landmark), F.lit(0)).otherwise(F.lit(MAX_HOPS)),
            F.least(distance, received),
        )
        program.message(sent, "src_to_dst", name=name).aggregate(F.min(received), name=name)
    program.participation("participates", initial_participation, changed)
    program.skip_destination_state().max_iterations(options.max_iterations)
    if options.vote_to_halt:
        program.vote_to_halt("active", changed)
    return program


def execute_sssp(
    graph: GraphAlgorithms,
    vertices: DataFrame,
    edges: DataFrame,
    *,
    options: PregelSsspOptions,
    cancellation: CancellationToken | None,
) -> GraphResult:
    """Execute weighted SSSP; output exactly `id: BIGINT, distance: DOUBLE?`."""
    if "weight" not in edges.columns or not isinstance(edges.schema["weight"].dataType, DoubleType):
        raise ValueError("SSSP requires a DOUBLE weight column")
    program = sssp_program(graph, options)

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        adjacency = (
            edges
            if options.directed
            else edges.unionByName(edges.select(F.col("dst").alias("src"), F.col("src").alias("dst"), "weight"))
        )
        outcome = program.loop(run, vertices, adjacency)
        if outcome.converged is False:
            raise ConvergenceError(f"sssp-pregel still had active vertices after {options.max_iterations} iterations")
        path, result = run.materialize(outcome.state.select("id", "distance"))
        handle = run.finish(
            path, result, algorithm="sssp-pregel", iterations=outcome.iterations, converged=outcome.converged
        )
        handle.method = "pregel"
        return handle

    return graph._run(
        vertices,
        edges,
        options.partitions,
        cancellation,
        body,
        edge_columns=("src", "dst", "weight"),
        count_vertices=False,
    )


def execute_landmarks(
    graph: GraphAlgorithms,
    vertices: DataFrame,
    edges: DataFrame,
    *,
    options: ShortestPathsOptions,
    cancellation: CancellationToken | None,
) -> GraphResult:
    """Execute per-landmark hops; an absent route is INT32 MAX, never null."""
    if len(set(options.landmarks)) != len(options.landmarks):
        raise ValueError("landmarks must be unique")
    program = landmarks_program(graph, options)

    def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        adjacency = (
            edges.select(F.col("dst").alias("src"), F.col("src").alias("dst")) if options.to_landmarks else edges
        )
        outcome = program.loop(run, vertices, adjacency)
        if outcome.converged is False:
            raise ConvergenceError(
                f"shortest-paths-pregel still had active vertices after {options.max_iterations} iterations"
            )
        columns = ["id", *["dist_" + str(landmark) for landmark in sorted(options.landmarks)]]
        path, result = run.materialize(outcome.state.select(*columns))
        handle = run.finish(
            path, result, algorithm="shortest-paths-pregel", iterations=outcome.iterations, converged=outcome.converged
        )
        handle.method = "pregel"
        return handle

    return graph._run(vertices, edges, options.partitions, cancellation, body, count_vertices=False)
