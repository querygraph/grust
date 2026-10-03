"""Relational graph algorithms; only bounded receipts/scalar reductions collect.

Pecan assumes a valid graph (README, "Valid graph contract"): BIGINT ids that
are unique and non-null, edges whose endpoints exist, finite non-negative
DOUBLE weights where weights are used. Nothing here checks those properties;
argument domains are validated once by the Pydantic option models.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast

from pyspark.sql.connect import functions as F
from pyspark.sql.types import LongType

from . import _contracts, pagerank_delta, pagerank_pregel_delta, pregel, shortest_pregel, traversal, wcc_randomized
from .lifecycle import CancellationToken, GraphCancelledError, GraphResult
from .staging import StagingRun
from .types import (
    EventKind,
    GraphOptions,
    IterationEvent,
    PageRankMethod,
    PageRankOptions,
    PregelSsspOptions,
    ShortestPathsOptions,
    TraversalMethod,
    TraversalOptions,
    WccMethod,
    WccOptions,
)
from .utils import GraphUtils

if TYPE_CHECKING:
    from pyspark.sql import DataFrame
    from pyspark.sql.connect.session import SparkSession

Observer = Callable[[IterationEvent], None]
ConvergenceError = _contracts.ConvergenceError
first_row = _contracts.first_row


class Body(Protocol):
    """An algorithm body: runs inside an owned staging run over the snapshotted inputs."""

    def __call__(self, run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult: ...


def _check_input_schema(spark: SparkSession, vertices: DataFrame, edges: DataFrame) -> None:
    """The one input check: column names and types, free of any job."""
    # The shared DataFrame annotation names the classic session even for
    # Connect frames. Identity is checked against the actual session object.
    if vertices.sparkSession is not cast(object, spark) or edges.sparkSession is not cast(object, spark):
        raise ValueError("vertices and edges must belong to this Spark session")
    for frame, columns in ((vertices, ("id",)), (edges, ("src", "dst"))):
        if len(frame.columns) != len(set(frame.columns)):
            raise ValueError("graph inputs require unique column names")
        for column in columns:
            if column not in frame.columns or not isinstance(frame.schema[column].dataType, LongType):
                raise ValueError(f"graph column {column!r} must have BIGINT type")


def _snapshot(run: StagingRun, vertices: DataFrame, edges: DataFrame,
              edge_columns: tuple[str, ...] = ("src", "dst"), *, vertex_columns: tuple[str, ...] = ("id",),
              count_vertices: bool = True, snapshot: bool = True) -> tuple[DataFrame, DataFrame, int | None]:
    """Project the inputs, and by default materialize them once as a stable copy.

    With snapshot=False the projected inputs are read where they are, every
    round: the caller vouches that they are stable and cheap to scan, which
    Parquet files and tables are and an expensive query is not. Nothing is
    written, so nothing is rewritten. The graph is assumed valid; no null,
    uniqueness or membership job runs. Count vertices only when the algorithm
    requests N (for example, 1/N terms).
    """
    vertices = vertices.select(*vertex_columns)
    edges = edges.select(*edge_columns)
    if snapshot:
        _, vertices = run.materialize(vertices)
        _, edges = run.materialize(edges)
    run.cancellation.check()
    return vertices, edges, vertices.count() if count_vertices else None


def physical_plan(frame: DataFrame) -> str:
    """The physical plan the server would execute for `frame`, as text (a diagnostic)."""
    # A private Connect DataFrame method; DataFrame.__getattr__ types unknown names as columns.
    text: str = cast(Any, frame)._explain_string(extended=True)
    marker = "== Physical Plan =="
    return text[text.index(marker):] if marker in text else text


class GraphAlgorithms:
    """Graph algorithms over BIGINT id/src/dst tables.

    Input tables are separately materialized once. This is stable during an
    algorithm, but is not an atomic snapshot across mutable sources. Results
    contain structural columns, not input properties.

    repartition_checkpoints=True keeps the keyless repartition before every
    staging write. False omits it as an explicit experiment, without declaring
    keyed partitioning on later reads or fixing the number of output files.
    """

    def __init__(self, spark: SparkSession, *, observer: Observer | None = None,
                 record_plans: bool = False, repartition_checkpoints: bool = True,
                 snapshot_inputs: bool = True) -> None:
        options = GraphOptions(record_plans=record_plans, repartition_checkpoints=repartition_checkpoints,
                               snapshot_inputs=snapshot_inputs)
        self.spark = spark
        self.utils = GraphUtils(spark)
        self.observer: Observer | None = observer
        self.repartition_checkpoints: bool = options.repartition_checkpoints
        # snapshot_inputs=False reads the given vertices and edges in place
        # instead of first rewriting them to Parquet in the run's staging area;
        # use it when the inputs already are stable files or tables.
        self.snapshot_inputs: bool = options.snapshot_inputs
        # With record_plans, an iteration's observer event carries the physical
        # plan of the frame the iteration materializes (one extra planning round
        # trip per iteration; the plan is text, not executed twice).
        self.record_plans: bool = options.record_plans

    def _observe(self, run: StagingRun, algorithm: str, step: int, kind: EventKind, *,
                 plan_of: DataFrame | None = None, **metrics: Any) -> None:
        if self.observer is not None:
            plan = physical_plan(plan_of) if plan_of is not None and self.record_plans else None
            self.observer(IterationEvent(kind=kind, algorithm=algorithm, iteration=step,
                                         run_path=run.path, plan=plan, **metrics))

    def _run(self, vertices: DataFrame, edges: DataFrame, partitions: int,
             cancellation: CancellationToken | None, body: Body, *,
             edge_columns: tuple[str, ...] = ("src", "dst"), vertex_columns: tuple[str, ...] = ("id",),
             count_vertices: bool = True) -> GraphResult:
        cancellation = cancellation or CancellationToken()
        cancellation.check()
        _check_input_schema(self.spark, vertices, edges)
        cancellation.attach(self.spark)
        run: StagingRun | None = None
        try:
            run = StagingRun(self.spark, self.utils, cancellation, partitions,
                             repartition_checkpoints=self.repartition_checkpoints)
            vertices, edges, size = _snapshot(run, vertices, edges, edge_columns, vertex_columns=vertex_columns,
                                             count_vertices=count_vertices, snapshot=self.snapshot_inputs)
            return body(run, vertices, edges, size)
        except BaseException as error:
            # Remove the query tag before issuing cleanup, so cancellation of
            # the algorithm cannot accidentally target its cleanup operation.
            cancellation.detach()
            terminal: BaseException = error
            if cancellation.cancelled and not isinstance(error, GraphCancelledError):
                terminal = GraphCancelledError("graph algorithm cancelled")
            if run is not None:
                terminal.run_path = run.path  # type: ignore[attr-defined]
                terminal.cleanup_deferred = run.write_uncertain  # type: ignore[attr-defined]
                message: str | None = None
                if run.write_uncertain:
                    message = (
                        f"write completion is uncertain; cleanup deferred for {run.path}. "
                        "The server session retains ownership and attempts cleanup at teardown; "
                        "this is best effort, not a guarantee that all writers have drained."
                    )
                else:
                    try:
                        run.close()
                    except Exception as cleanup_error:  # noqa: BLE001 — preserve the original failure if cleanup fails.
                        terminal.cleanup_deferred = True  # type: ignore[attr-defined]
                        message = f"graph cleanup failed; session teardown will retry: {cleanup_error}"
                if message is not None:
                    if hasattr(terminal, "add_note"):
                        terminal.add_note(message)
                    else:
                        warnings.warn(message, RuntimeWarning, stacklevel=2)
            if terminal is not error:
                raise terminal from error
            raise
        finally:
            cancellation.detach()

    def pagerank(self, vertices: DataFrame, edges: DataFrame, *, reset_probability: float = 0.15,
                 max_iterations: int = 20, tolerance: float | None = None, partitions: int = 4,
                 cancellation: CancellationToken | None = None, method: PageRankMethod = "power",
                 normalize: bool = False, vote_to_halt: bool = False) -> GraphResult:
        """Directed PageRank with uniform restart, in four forms.

        Initialize rank=1/N. At each step, redistribute dangling rank uniformly,
        then set rank(v)=reset/N+(1-reset)*(incoming(v)+dangling/N). Parallel edges
        count separately; self-loops and isolated vertices are retained.

        The default method="power" performs exactly max_iterations when
        tolerance=None (converged=None), or stops at L1 rank change <= tolerance.
        method="delta" retains unsent residual and pushes a tolerance-scaled
        active frontier; inactive vertices can accumulate updates and reactivate.
        It requires a positive tolerance and certifies the normalized output's
        full fixed-point L1 residual. Its result exposes residual/error_bound.
        Set an explicit larger cap, e.g. 1000, for strict delta tolerances.
        Frontier joins can still scan the edge table. Both tolerance-controlled
        methods raise ConvergenceError at the limit. Output: id BIGINT,
        pagerank DOUBLE. Fixed-step power behavior remains unchanged.

        method="pregel" is the form of the Pregel paper and of GraphX's static
        PageRank: rank(v)=reset/N+(1-reset)*incoming(v) for exactly
        max_iterations, no dangling redistribution and no convergence test, so
        a step is one job. The ranks then sum to less than one when dangling
        vertices exist; normalize=True divides by the total at the end. The
        LDBC Graphalytics contract is "power" (it redistributes dangling rank).

        method="pregel_delta" is GraphX's dynamic PageRank in the form of
        graphframes-rs: rank and delta start at reset, a vertex whose delta
        exceeds tolerance sends delta/out_degree, and a vertex adds
        (1-reset)*received to its rank and takes that gain as its new delta.
        The frontier shrinks as vertices settle. There is no dangling term and
        no certificate, and a step is one job. Ranks are on GraphX's scale (a
        vertex starts at reset, not reset/N) and tolerance, which is required,
        compares to one vertex's gain on that scale; normalize=True divides by
        the total. It runs exactly max_iterations steps (converged=None), or,
        with vote_to_halt=True, stops when no delta exceeds tolerance and
        raises ConvergenceError at the limit.
        """
        options = PageRankOptions(reset_probability=reset_probability, max_iterations=max_iterations,
                                  tolerance=tolerance, partitions=partitions, method=method, normalize=normalize,
                                  vote_to_halt=vote_to_halt)
        if options.vote_to_halt and options.method != "pregel_delta":
            raise ValueError("vote_to_halt applies only to method='pregel_delta'")
        if options.method == "pregel_delta":
            return pagerank_pregel_delta.execute(self, vertices, edges, options=options, cancellation=cancellation)
        if options.method == "delta":
            if options.tolerance is None:
                raise ValueError("delta PageRank requires a positive tolerance")
            return pagerank_delta.execute(self, vertices, edges, options=options, cancellation=cancellation)
        if options.method == "pregel":
            return self._pagerank_pregel(vertices, edges, options, cancellation)

        reset = options.reset_probability
        damping = 1.0 - reset
        tolerance_value = options.tolerance

        def execute(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
            assert size is not None  # PageRank requests N for normalization.
            if not size:
                path, result = run.materialize(vertices.withColumn("pagerank", F.lit(0.0)))
                return run.finish(path, result, algorithm="pagerank", iterations=0, converged=True)
            _, weighted = run.materialize(
                edges.join(edges.groupBy("src").count().withColumnRenamed("count", "degree"), "src")
            )
            # Static dangling vertices need no per-iteration anti-join.
            _, dangling = run.materialize(
                vertices.join(edges.select(F.col("src").alias("id")).distinct(), "id", "left_anti")
            )
            path, rank = run.materialize(vertices.withColumn("pagerank", F.lit(1.0 / size)))
            converged: bool | None = None if tolerance_value is None else False
            step = 0
            for step in range(1, options.max_iterations + 1):
                run.cancellation.check()
                self._observe(run, "pagerank", step, "iteration_start")
                run.cancellation.check()
                dangling_mass: float = first_row(rank.join(dangling, "id").agg(F.sum("pagerank")))[0] or 0.0
                message = weighted.join(rank, weighted.src == rank.id).select(
                    weighted.dst.alias("id"), (rank.pagerank / weighted.degree).alias("message")
                ).groupBy("id").agg(F.sum("message").alias("incoming"))
                updated = vertices.join(message, "id", "left").select(
                    "id", (F.lit(reset / size) + F.lit(damping) * (
                        F.coalesce(F.col("incoming"), F.lit(0.0)) + F.lit(dangling_mass / size)
                    )).alias("pagerank"),
                )
                next_path, next_rank = run.materialize(updated)
                if tolerance_value is not None:
                    run.cancellation.check()
                    before = rank.select("id", F.col("pagerank").alias("before"))
                    change: float = first_row(next_rank.join(before, "id").agg(
                        F.sum(F.abs(F.col("pagerank") - F.col("before")))
                    ))[0]
                    converged = change <= tolerance_value
                run.remove(path)
                path, rank = next_path, next_rank
                self._observe(run, "pagerank", step, "iteration_end")
                if converged:
                    break
            if converged is False:
                raise ConvergenceError(f"PageRank did not reach tolerance in {options.max_iterations} iterations")
            return run.finish(path, rank, algorithm="pagerank", iterations=step, converged=converged)

        return self._run(vertices, edges, options.partitions, cancellation, execute)

    def _pagerank_pregel(self, vertices: DataFrame, edges: DataFrame, options: PageRankOptions,
                         cancellation: CancellationToken | None) -> GraphResult:
        reset = options.reset_probability
        damping = 1.0 - reset

        def execute(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
            assert size is not None  # the restart term is reset/N.
            if not size:
                path, result = run.materialize(vertices.withColumn("pagerank", F.lit(0.0)))
                return run.finish(path, result, algorithm="pagerank-pregel", iterations=0, converged=None)
            _, weighted = run.materialize(
                edges.join(edges.groupBy("src").count().withColumnRenamed("count", "degree"), "src")
            )
            path, rank = run.materialize(vertices.withColumn("pagerank", F.lit(1.0 / size)))
            step = 0
            for step in range(1, options.max_iterations + 1):
                run.cancellation.check()
                self._observe(run, "pagerank-pregel", step, "iteration_start")
                message = weighted.join(rank, weighted.src == rank.id).select(
                    weighted.dst.alias("id"), (rank.pagerank / weighted.degree).alias("message")
                ).groupBy("id").agg(F.sum("message").alias("incoming"))
                updated = vertices.join(message, "id", "left").select(
                    "id", (F.lit(reset / size) + F.lit(damping) * F.coalesce(F.col("incoming"), F.lit(0.0)))
                    .alias("pagerank"))
                next_path, next_rank = run.materialize(updated)
                run.remove(path)
                path, rank = next_path, next_rank
                self._observe(run, "pagerank-pregel", step, "iteration_end")
            if options.normalize:
                total: float = first_row(rank.agg(F.sum("pagerank")))[0]
                normalized = rank.select("id", (F.col("pagerank") / F.lit(total)).alias("pagerank"))
                next_path, rank = run.materialize(normalized)
                run.remove(path)
                path = next_path
            return run.finish(path, rank, algorithm="pagerank-pregel", iterations=step, converged=None)

        return self._run(vertices, edges, options.partitions, cancellation, execute)

    def pregel(self, *, algorithm: str = "pregel") -> pregel.Pregel:
        """A Pregel program over this session, in the form of graphframes-rs's builder.

        Declare vertex columns, messages and an aggregate on the returned
        program, then call its run(vertices, edges). See the pregel module.
        """
        return pregel.Pregel(self, algorithm=algorithm)

    def wcc(self, vertices: DataFrame, edges: DataFrame, *, max_iterations: int = 100, partitions: int = 4,
            cancellation: CancellationToken | None = None, method: WccMethod = "min_label",
            seed: int = 42, canonical_labels: bool = True) -> GraphResult:
        """Exact weak components by propagation or seeded randomized contraction.

        Treat every edge as undirected. The default method="min_label"
        starts each vertex with its own ID and repeatedly takes the minimum of each
        vertex's own and its neighbors' labels, stopping at a fixed point.
        method="randomized" contracts the graph with fresh affine maps over
        GF(2^64) each round (Bögeholz, Brand and Todor, ICDE 2020): every vertex
        takes the minimum hashed id of its closed neighbourhood as its
        representative, edges are relabelled until none remain, and the rounds
        are unwound by composing the later maps. It requires the axpb capability
        and an unsigned 64-bit seed (default 42). "randomized_fused" is an alias
        kept for older configurations. max_iterations limits propagation or
        contraction rounds. With canonical_labels (the default) a component is
        labelled by its minimum ID; canonical_labels=False keeps the hashed
        labels, which name the same partition, and skips one aggregate and one
        join. Isolates label themselves. Reaching the cap raises ConvergenceError.
        Output: id BIGINT, component BIGINT.
        """
        options = WccOptions(max_iterations=max_iterations, partitions=partitions, method=method, seed=seed,
                             canonical_labels=canonical_labels)
        if options.method in ("randomized", "randomized_fused"):
            return wcc_randomized.execute(self, vertices, edges, options=options, cancellation=cancellation)

        def execute(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
            _, adjacency = run.materialize(edges.unionByName(
                edges.select(F.col("dst").alias("src"), F.col("src").alias("dst"))
            ).distinct())
            path, labels = run.materialize(vertices.withColumn("component", F.col("id")))
            if not labels.limit(1).count():
                return run.finish(path, labels, algorithm="wcc-min-label", iterations=0, converged=True)
            for step in range(1, options.max_iterations + 1):
                run.cancellation.check()
                self._observe(run, "wcc-min-label", step, "iteration_start")
                run.cancellation.check()
                messages = adjacency.join(labels, adjacency.src == labels.id).select(
                    adjacency.dst.alias("id"), labels.component
                )
                updated = labels.unionByName(messages).groupBy("id").agg(F.min("component").alias("component"))
                next_path, next_labels = run.materialize(updated)
                before = labels.select("id", F.col("component").alias("before"))
                changed: int = next_labels.join(before, "id").where(
                    F.col("component") != F.col("before")).limit(1).count()
                run.remove(path)
                path, labels = next_path, next_labels
                self._observe(run, "wcc-min-label", step, "iteration_end")
                if not changed:
                    return run.finish(path, labels, algorithm="wcc-min-label", iterations=step, converged=True)
            raise ConvergenceError(f"WCC did not reach a fixed point in {options.max_iterations} iterations")

        return self._run(vertices, edges, options.partitions, cancellation, execute, count_vertices=False)

    def bfs(self, vertices: DataFrame, edges: DataFrame, *, source: int, method: TraversalMethod = "frontier",
            directed: bool = True, max_iterations: int = 1000, partitions: int = 4,
            cancellation: CancellationToken | None = None) -> GraphResult:
        """Single-source hop distances and a parent tree; unreachable rows are null.

        method="reference" relaxes all reached vertices each round; "frontier"
        expands only changed vertices. "push_pull" switches relational join
        orientation; it does not promise native adjacency early exit.
        The source is assumed to exist and has parent=source.
        The cap includes the final round certifying no further changes.
        """
        options = TraversalOptions(source=source, method=method, directed=directed,
                                   max_iterations=max_iterations, partitions=partitions)
        if options.method in ("delta_star", "pregel"):
            raise ValueError("unsupported traversal method")
        return traversal.execute(self, vertices, edges, options=options, weighted=False, cancellation=cancellation)

    def sssp(self, vertices: DataFrame, edges: DataFrame, *, source: int, method: TraversalMethod = "frontier",
             directed: bool = True, max_iterations: int = 1000, partitions: int = 4,
             cancellation: CancellationToken | None = None, delta: float = 1.0,
             vote_to_halt: bool = True) -> GraphResult:
        """Single-source shortest distances for finite nonnegative DOUBLE weights.

        Edges require a `weight` column. Reference is synchronous Bellman–Ford;
        frontier relaxes only changed vertices. "delta_star" processes the lowest
        pending distance bucket with width delta, relaxing all outgoing edges;
        this differs from classical light/heavy delta-stepping. Equal-distance
        paths prefer fewer hops, then the smaller parent ID, preventing parent
        cycles on zero-weight edges. Unreachable distance/parent/hops are null.
        Weights are assumed finite and non-negative and distance sums are
        assumed finite (the valid graph contract); nothing checks them.
        Both methods require an explicit convergence certificate.

        method="pregel" runs a distance-only active-source Pregel program with
        one DOUBLE message, MIN, and one state write per superstep. Its output
        is id BIGINT, distance DOUBLE? (no parent/hops). vote_to_halt=True counts
        active vertices after each step and raises if the cap precedes a halt.
        False runs exactly max_iterations supersteps and returns that possibly
        incomplete state with converged=None; it runs no activity count.
        """
        if method == "pregel":
            pregel_options = PregelSsspOptions(source=source, directed=directed, max_iterations=max_iterations,
                                              partitions=partitions, vote_to_halt=vote_to_halt)
            return shortest_pregel.execute_sssp(self, vertices, edges, options=pregel_options,
                                                cancellation=cancellation)
        if not vote_to_halt:
            raise ValueError("vote_to_halt=False applies only to method='pregel'")
        options = TraversalOptions(source=source, method=method, directed=directed,
                                   max_iterations=max_iterations, partitions=partitions, delta=delta)
        if options.method == "push_pull":
            raise ValueError("unsupported traversal method")
        return traversal.execute(self, vertices, edges, options=options, weighted=True, cancellation=cancellation)

    def shortest_paths(self, vertices: DataFrame, edges: DataFrame, *, landmarks: Sequence[int],
                       to_landmarks: bool = False, max_iterations: int = 1000, partitions: int = 4,
                       vote_to_halt: bool = True, cancellation: CancellationToken | None = None) -> GraphResult:
        """Unweighted per-landmark hops, as graphframes-rs's shortest_paths.

        Edges are directed: default distances run from each landmark to the
        vertex; to_landmarks=True reverses edges. Output is id BIGINT and one
        INT32 dist_<landmark> column per unique landmark, in sorted landmark
        order. Unreachable is 2^31-1. Landmarks must be graph vertices, assumed
        by contract without a membership job. With vote_to_halt, the cap
        includes the final no-change step and raises if still active. False
        returns the fixed-budget state and converged=None, counting nothing.
        """
        options = ShortestPathsOptions(landmarks=tuple(landmarks), to_landmarks=to_landmarks,
                                       max_iterations=max_iterations, partitions=partitions,
                                       vote_to_halt=vote_to_halt)
        return shortest_pregel.execute_landmarks(self, vertices, edges, options=options, cancellation=cancellation)
