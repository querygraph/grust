"""A Pregel loop over Sail tables, in the form of graphframes-rs's `PregelBuilder`.

A program declares vertex columns (an initial and an update expression each),
messages along the edges, how messages to one vertex are aggregated, and
optionally a participation column and a vote to halt. One superstep is

    triplets   = sources JOIN edges [JOIN destinations]
    messages   = one row per triplet and message, addressed to an endpoint
    aggregated = messages grouped by the addressed vertex
    state      = state LEFT JOIN aggregated, every column set by its update

as in `src/algorithm/pregel.rs` of graphframes-rs, which follows GraphX and
GraphFrames. Expressions name their inputs through `src`, `dst`, `edge` and
`msg`. A vertex that receives nothing sees null messages.

With `skip_destination_state` only the sources that participate are joined
to the edges, so the frontier shrinks the join. With destination state a
triplet is kept while either endpoint participates. A vote to halt counts
the active vertices after a step and stops at zero; without one the loop
runs `max_iterations` steps and counts nothing.

The state is the only relation a step writes, so a step is one job.
graphframes-rs also checkpoints the aggregated messages; the result is the
same. The graph is assumed valid; nothing here checks it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pyspark.sql.connect import functions as F

if TYPE_CHECKING:
    from pyspark.sql import Column, DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun

Direction = Literal["src_to_dst", "dst_to_src", "bidirectional"]

_SRC = "__pregel_msg_src_"
_DST = "__pregel_msg_dst_"
_EDGE = "__pregel_msg_edge_"
_MSG = "__pregel_msg_"
_TARGETS: dict[Direction, tuple[str, ...]] = {
    "src_to_dst": ("dst",), "dst_to_src": ("src",), "bidirectional": ("src", "dst")}


def src(name: str) -> Column:
    """A column of the source vertex's state, in a message expression."""
    return F.col(_SRC + name)


def dst(name: str) -> Column:
    """A column of the destination vertex's state; needs destination state."""
    return F.col(_DST + name)


def edge(name: str) -> Column:
    """An edge column, in a message expression."""
    return F.col(_EDGE + name)


def msg(name: str = "msg") -> Column:
    """A message: one sent value in an aggregate, the aggregated value in an update."""
    return F.col(_MSG + name)


@dataclass(frozen=True, slots=True)
class VertexColumn:
    name: str
    initial: Column
    update: Column


@dataclass(frozen=True, slots=True)
class Message:
    name: str
    expression: Column
    direction: Direction


@dataclass(frozen=True, slots=True)
class Outcome:
    """The last written state of a loop. `converged` is None without a vote to halt."""

    path: str
    state: DataFrame
    iterations: int
    converged: bool | None


class Pregel:
    """A Pregel program. Configure it, then `run` it or call `loop` inside an owned run."""

    def __init__(self, graph: GraphAlgorithms, *, algorithm: str = "pregel") -> None:
        self.graph = graph
        self.algorithm: str = algorithm
        self.columns: list[VertexColumn] = []
        self.messages: list[Message] = []
        self.aggregates: list[Column] = []
        self.edge_columns: list[str] = ["src", "dst"]
        self.participation_column: VertexColumn | None = None
        self.vote: tuple[str, Column] | None = None
        self.destination_state: bool = True
        self.limit: int | None = None

    def vertex_column(self, name: str, initial: Column, update: Column) -> Pregel:
        self.columns.append(VertexColumn(name, initial, update))
        return self

    def edge_column(self, name: str) -> Pregel:
        if name not in self.edge_columns:
            self.edge_columns.append(name)
        return self

    def message(self, expression: Column, direction: Direction, *, name: str = "msg") -> Pregel:
        self.messages.append(Message(name, expression, direction))
        return self

    def aggregate(self, expression: Column, *, name: str = "msg") -> Pregel:
        self.aggregates.append(expression.alias(_MSG + name))
        return self

    def participation(self, name: str, initial: Column, update: Column) -> Pregel:
        self.participation_column = VertexColumn(name, initial, update)
        return self

    def vote_to_halt(self, name: str, active: Column) -> Pregel:
        """Stop when `active` is false for every vertex after a step; all are active at the start."""
        self.vote = (name, active)
        return self

    def skip_destination_state(self) -> Pregel:
        self.destination_state = False
        return self

    def max_iterations(self, limit: int) -> Pregel:
        if limit < 0:
            raise ValueError("max_iterations must not be negative")
        self.limit = limit
        return self

    def loop(self, run: StagingRun, vertices: DataFrame, edges: DataFrame) -> Outcome:
        """Run the supersteps inside `run`; the caller owns the run and finishes it."""
        if not self.messages:
            raise ValueError("a Pregel program needs at least one message")
        if not self.aggregates and len(self.messages) > 1:
            raise ValueError("several messages need an aggregate expression")
        if self.limit is None and self.vote is None:
            raise ValueError("a Pregel program needs max_iterations or a vote to halt")

        state = vertices
        for column in self.columns:
            state = state.withColumn(column.name, column.initial)
        updates = [column.update.alias(column.name) for column in self.columns]
        if self.vote is not None:
            state = state.withColumn(self.vote[0], F.lit(True))
            updates.append(self.vote[1].alias(self.vote[0]))
        participation = self.participation_column
        if participation is not None:
            state = state.withColumn(participation.name, participation.initial)
            updates.append(participation.update.alias(participation.name))
        updates.append(F.col("id"))
        triplet_edges = edges.select(*[F.col(name).alias(_EDGE + name) for name in self.edge_columns])

        path, state = run.materialize(state)
        iteration = 0
        converged: bool | None = None if self.vote is None else False
        while (self.limit is None or iteration < self.limit) and not converged:
            iteration += 1
            run.cancellation.check()
            sources = state
            if not self.destination_state and participation is not None:
                sources = sources.where(F.col(participation.name))
            triplets = _prefixed(sources, _SRC).join(triplet_edges, F.col(_SRC + "id") == F.col(_EDGE + "src"))
            if self.destination_state:
                triplets = triplets.join(_prefixed(state, _DST), F.col(_DST + "id") == F.col(_EDGE + "dst"))
                if participation is not None:
                    triplets = triplets.where(F.col(_SRC + participation.name) | F.col(_DST + participation.name))
            sent = [triplets.select(F.col(_EDGE + target).alias("id"), message.expression.alias(_MSG + message.name))
                    for message in self.messages for target in _TARGETS[message.direction]]
            messages = sent[0]
            for part in sent[1:]:
                messages = messages.unionByName(part, allowMissingColumns=True)
            aggregated = messages.groupBy("id").agg(*self.aggregates) if self.aggregates else messages
            received = aggregated.withColumnRenamed("id", "__pregel_to")
            updated = state.join(received, F.col("id") == F.col("__pregel_to"), "left").select(*updates)
            self.graph._observe(run, self.algorithm, iteration, "iteration_start", plan_of=updated)
            next_path, next_state = run.materialize(updated)
            run.remove(path)
            path, state = next_path, next_state
            if self.vote is None:
                self.graph._observe(run, self.algorithm, iteration, "iteration_end")
            else:
                run.cancellation.check()
                active: int = state.where(F.col(self.vote[0])).count()
                converged = active == 0
                self.graph._observe(run, self.algorithm, iteration, "iteration_end", frontier_size=active)
        return Outcome(path, state, iteration, converged)

    def run(self, vertices: DataFrame, edges: DataFrame, *, partitions: int = 4,
            cancellation: CancellationToken | None = None, include_debug_columns: bool = False) -> GraphResult:
        """Run the program; the result holds the vertex columns and `id`.

        `vertices` may carry attribute columns for the initial expressions to
        read. With `include_debug_columns` the vote and participation columns
        are kept. Reaching `max_iterations` with a vote still active returns
        `converged=False`; it does not raise.
        """
        attributes = tuple(vertices.columns)

        def body(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
            outcome = self.loop(run, vertices, edges)
            path, result = outcome.path, outcome.state
            kept = [*[column.name for column in self.columns], "id"]
            if not include_debug_columns and result.columns != kept:
                path, result = run.materialize(result.select(*kept))
            return run.finish(path, result, algorithm=self.algorithm, iterations=outcome.iterations,
                              converged=outcome.converged)

        return self.graph._run(vertices, edges, partitions, cancellation, body, vertex_columns=attributes,
                               edge_columns=tuple(self.edge_columns), count_vertices=False)


def _prefixed(frame: DataFrame, prefix: str) -> DataFrame:
    return frame.select(*[F.col(name).alias(prefix + name) for name in frame.columns])
