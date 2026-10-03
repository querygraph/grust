"""Seeded randomized contraction with affine-hashed representatives.

The algorithm is Bögeholz, Brand and Todor, "In-database connected component
analysis" (ICDE 2020), in the form graphframes-rs implements it: every round
draws an affine map f(x) = a*x + b over GF(2^64) with a != 0 (a permutation of
the 64-bit ids), each vertex takes the minimum of f over its closed
neighbourhood as its representative, and the edges are relabelled by those
representatives until none remain. Representatives are the hashed ids
themselves, so a round is one union, one grouped minimum and a `least`: no
priority table, no `min_by`, no join to recover an original id.

The back pass unwinds the rounds: a representative that was forwarded takes
the later round's label; one that dropped out (its id had no edge in later
rounds) is pushed into the final id space by the composition of the later
affine maps, computed on the client in the same field. Every final label is
the image, under the composition of all rounds' maps, of some original vertex
of its component; a vertex with no edge takes its own image under that same
composition, so all labels live in one id space and distinct components never
share one. The default then relabels each component by the minimum original
id of its members (one aggregate and one join), which `canonical_labels=False`
skips, because any label set names the same partition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F

from ._contracts import ConvergenceError
from .types import MASK, ContractionStep

if TYPE_CHECKING:
    from pyspark.sql import Column, DataFrame

    from .algorithms import GraphAlgorithms
    from .lifecycle import CancellationToken, GraphResult
    from .staging import StagingRun
    from .types import WccOptions

# GF(2^64) with the reduction polynomial x^64 + x^4 + x^3 + x + 1, the field of
# the server's `gf_axpb`; the client needs it only for scalar coefficients.
_REDUCTION = 0x1B


def signed(value: int) -> int:
    """The signed 64-bit reading of an unsigned 64-bit pattern (BIGINT on the wire)."""
    return value if value < (1 << 63) else value - (1 << 64)


def unsigned(value: int) -> int:
    return value & MASK


def gf_multiply(a: int, x: int) -> int:
    """Carry-less multiplication of two unsigned 64-bit field elements."""
    a &= MASK
    x &= MASK
    result = 0
    for _ in range(64):
        if x & 1:
            result ^= a
        high = a >> 63
        a = ((a << 1) & MASK) ^ (_REDUCTION if high else 0)
        x >>= 1
    return result


def gf_axpb(a: int, x: int, b: int) -> int:
    """`a*x + b` in the field, on unsigned patterns; the server function on one scalar."""
    return gf_multiply(a, x) ^ unsigned(b)


@dataclass(slots=True)
class SplitMix64:
    """Version-independent coefficient stream shared with the native kernel.

    The seed is validated by `WccOptions` (an unsigned 64-bit integer).
    """

    state: int

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK
        return value ^ (value >> 31)

    def coefficients(self) -> tuple[int, int]:
        """A nonzero `a` and any `b`, as signed BIGINT literals."""
        a = self.next()
        while a == 0:
            a = self.next()
        return signed(a), signed(self.next())


def _axpb(a: int, column: str, b: int) -> Column:
    return F.call_function("gf_axpb", F.lit(a).cast("long"), F.col(column), F.lit(b).cast("long"))


def representatives(edges: DataFrame, a: int, b: int) -> DataFrame:
    """`rep(v) = least(f(v), min over neighbours u of f(u))` for every endpoint v.

    One union of the two edge projections, one grouped minimum, one `least`.
    Isolated vertices do not appear: they are their own representative.
    """
    forward = edges.select(F.col("src").alias("id"), _axpb(a, "dst", b).alias("neighbour"))
    reverse = edges.select(F.col("dst").alias("id"), _axpb(a, "src", b).alias("neighbour"))
    minima = forward.unionByName(reverse).groupBy("id").agg(F.min("neighbour").alias("neighbour"))
    return minima.select("id", F.least(_axpb(a, "id", b), F.col("neighbour")).alias("representative"))


def relabel(edges: DataFrame, reps: DataFrame) -> DataFrame:
    """Edges `(rep(u), rep(w))` with the self-loops of the contraction dropped, deduplicated."""
    by_source = reps.select(F.col("id").alias("old_src"), F.col("representative").alias("new_src"))
    by_target = reps.select(F.col("id").alias("old_dst"), F.col("representative").alias("new_dst"))
    relabelled = edges.join(by_source, edges.src == by_source.old_src).select(
        F.col("new_src").alias("src"), F.col("dst"))
    return relabelled.join(by_target, (relabelled.dst == by_target.old_dst) &
                           (relabelled.src != by_target.new_dst)).select(
        "src", F.col("new_dst").alias("dst")).distinct()


def unwind(older: DataFrame, frontier: DataFrame, acc_a: int, acc_b: int) -> DataFrame:
    """One back-propagation step.

    `older` holds round t's `(id, representative)` with representatives in round
    t+1's id space; `frontier` holds round t+1's ids already expressed in the
    final space. A forwarded representative takes the frontier's label; one
    that dropped out is mapped by the composition of rounds t+1.. of the affine
    maps, `(acc_a, acc_b)`.
    """
    later = frontier.select(F.col("id").alias("later_id"), F.col("representative").alias("later_rep"))
    joined = older.join(later, older.representative == later.later_id, "left")
    pushed = F.call_function("gf_axpb", F.lit(acc_a).cast("long"), F.col("representative"),
                             F.lit(acc_b).cast("long"))
    return joined.select(older.id.alias("id"), F.coalesce(F.col("later_rep"), pushed).alias("representative"))


def execute(graph: GraphAlgorithms, vertices: DataFrame, edges: DataFrame, *, options: WccOptions,
            cancellation: CancellationToken | None) -> GraphResult:
    random = SplitMix64(options.seed)
    if "axpb" not in graph.utils.capabilities:
        raise ValueError("randomized WCC requires the axpb capability")
    algorithm = "wcc-randomized-contraction"

    def contract(run: StagingRun, vertices: DataFrame, edges: DataFrame, size: int | None) -> GraphResult:
        # The snapshot's edges, oriented and possibly duplicated, serve the
        # first round as they are: the representative union reads both
        # directions, and the first relabelling deduplicates.
        edge_path: str | None = None
        current = edges.where(F.col("src") != F.col("dst"))
        run.cancellation.check()
        remaining: int = current.count()
        history: list[tuple[str, DataFrame]] = []
        coefficients: list[tuple[int, int]] = []
        steps: list[ContractionStep] = []
        while remaining:
            if len(history) >= options.max_iterations:
                raise ConvergenceError(f"WCC contraction did not finish in {options.max_iterations} iterations")
            step = len(history) + 1
            run.cancellation.check()
            graph._observe(run, algorithm, step, "iteration_start")
            a, b = random.coefficients()
            rep_path, reps = run.materialize(representatives(current, a, b))
            history.append((rep_path, reps))
            coefficients.append((a, b))
            next_path, next_edges = run.materialize(relabel(current, reps))
            run.cancellation.check()
            next_count: int = next_edges.count()
            if edge_path is not None:
                run.remove(edge_path)
            edge_path, current = next_path, next_edges
            record = ContractionStep(active_vertices=0, edges_before=remaining, edges_after=next_count,
                                     coefficient_a=a, coefficient_b=b)
            steps.append(record)
            graph._observe(run, algorithm, step, "iteration_end", **record.model_dump())
            remaining = next_count
        if edge_path is not None:
            run.remove(edge_path)

        if history:
            # Back pass: start from the last round's representatives, which are
            # already in the final id space, and unwind one round at a time.
            frontier_path, frontier = history[-1]
            acc_a, acc_b = 1, 0
            for t in range(len(history) - 2, -1, -1):
                run.cancellation.check()
                later_a, later_b = coefficients[t + 1]
                acc_a, acc_b = (signed(gf_multiply(acc_a, later_a)),
                                signed(gf_axpb(acc_a, later_b, acc_b)))
                older_path, older = history[t]
                unwound_path, unwound = run.materialize(unwind(older, frontier, acc_a, acc_b))
                run.remove(frontier_path)
                run.remove(older_path)
                frontier_path, frontier = unwound_path, unwound
            # Every component label in the final space is F(u) for an original
            # vertex u of that component, F being the composition of all rounds'
            # maps and a bijection. A vertex with no edge therefore takes F(v):
            # the same id space, and distinct from every other label. Labelling
            # it with its own original id instead would mix two id spaces, and a
            # hashed label could then equal an isolated vertex's id.
            first_a, first_b = coefficients[0]
            full_a, full_b = (signed(gf_multiply(acc_a, first_a)),
                              signed(gf_axpb(acc_a, first_b, acc_b)))
            own_image = F.call_function("gf_axpb", F.lit(full_a).cast("long"), F.col("id"),
                                        F.lit(full_b).cast("long"))
            labelled = vertices.join(frontier, "id", "left").select(
                "id", F.coalesce(F.col("representative"), own_image).alias("component"))
        else:
            labelled = vertices.select("id", F.col("id").alias("component"))

        if options.canonical_labels:
            _, raw = run.materialize(labelled)
            minima = raw.groupBy("component").agg(F.min("id").alias("minimum_id"))
            labelled = raw.join(minima, "component").select("id", F.col("minimum_id").alias("component"))
        path, result = run.materialize(labelled)
        handle = run.finish(path, result, algorithm=algorithm, iterations=len(history), converged=True)
        handle.method = options.method
        handle.seed = options.seed
        handle.contractions = steps
        return handle

    return graph._run(vertices, edges, options.partitions, cancellation, contract, count_vertices=False)
