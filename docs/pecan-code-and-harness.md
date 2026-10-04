# Pecan code and measurement harness — reading map for Sem

Pecan's implementation and benchmark harness live in the public
[`querygraph/sail`](https://github.com/querygraph/sail) fork. Grust holds the
review reports. Start with the DeltaStar loop and the timed adapter below.

There are three layers, with different responsibilities:

1. **Algorithm:** Python DataFrame operations in `pyspark_pecan` build and run
   the SSSP iterations. Start at `traversal_stepping.py`.
2. **Measurement:** `traversal_cell.py` calls the algorithm and records elapsed
   time; `measurement.py` samples process/container memory.
3. **Engine optimization:** `compact_struct_min.rs` changes how our Sail fork
   stores one SQL aggregate's state. Its purpose and evidence appear below.

## Which version to read

| Purpose | Source |
|---|---|
| Integrated typed Pecan review version | [`6ae2e43a9`, package directory](https://github.com/querygraph/sail/tree/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan), published on `work/stream-review-followup` |
| Exact Python implementation and harness used for the 33.05 GiB scale-24 result | [`3a9028057`, package directory](https://github.com/querygraph/sail/tree/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/graph-algorithms/src/pyspark_pecan) |
| Sail runtime used for that result | [`56194b170`, Sail fork commit](https://github.com/querygraph/sail/commit/56194b170155301ba91077f0ba3df31fe2c78b6b); includes the engine optimization explained below |

These are intentionally separate pins. The current code integrates the Pydantic
rewrite with the newer runtime, ownership and certificate fixes. It assumes
valid graph input, removes input-audit queries, and retains the optional
checkpoint repartition switch (enabled by default). The scale-24 result
predates these Python changes. See the [integration evidence](reviews/pecan-validation-2026-10-01/README.md) for the exact tested boundary.

## Current Pecan code

All paths below are under `examples/extensions/graph-algorithms/src/pyspark_pecan/`
at `6ae2e43a9`.

| Read | File and responsibility |
|---|---|
| 1 | [`algorithms.py:310–329`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L310-L329): public `GraphAlgorithms.sssp` parameters, Pydantic validation and dispatch |
| 2 | [`types.py`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/types.py): typed options, events and contraction records; arguments are validated once |
| 3 | [`traversal.py`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal.py): weight schema, undirected edge expansion, adjacency materialization and reference/frontier loops |
| 4 | [`traversal_stepping.py`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal_stepping.py): complete DeltaStar loop, `state.unionByName(candidates)`, grouped `min(struct(...))`, label updates and pending queue; 67 lines |
| 5 | [`traversal_state.py`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal_state.py): lazy one-row seed with exact BIGINT literals; no vertex scan |
| 6 | [`staging.py`](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/staging.py): checkpoint repartition, Parquet write/read, ownership and generation cleanup |

The DeltaStar method selects the lowest pending distance bucket and relaxes
all outgoing edges of its selected vertices. It is not classical light/heavy
delta-stepping. Each round combines candidates with all reached labels before
grouping, so a small active frontier does not make the entire plan small.

## Harness behind the reported measurement

These links all pin `3a9028057`, the actual measured controller, under
`examples/extensions/benchmarks/`.

| Part | Exact location |
|---|---|
| Parse parameters | [`graph_cell.py:371–421`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/graph_cell.py#L371-L421) |
| Launch Sail and connect the client | [`graph_cell.py:471–494`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/graph_cell.py#L471-L494), with process setup in [`runtime.py`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/runtime.py) |
| Read input, call algorithm, time it, write result | **[`traversal_cell.py:19–104`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/traversal_cell.py#L19-L104)** — 86 lines across the traversal adapters; Pecan's branch is **83–97** |
| Read container memory counters and process RSS/PSS | [`measurement.py:35–73`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/measurement.py#L35-L73); sampling starts at [`Sampler`, line 95](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/measurement.py#L95) |
| Validate after execution | [`graph_cell.py:494–513`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/graph_cell.py#L494-L513) calls [`traversal_cell.validate`](https://github.com/querygraph/sail/blob/3a9028057c6c6c5034492845926fc4bc18f9626f/examples/extensions/benchmarks/traversal_cell.py#L107-L119) |

The complete campaign harness is larger than 100 lines: it also owns input
identity checks, process lifecycle, correctness verification and failure
receipts. The timed traversal adapter above is the short path to inspect.

The timer starts at `traversal_cell.py:27`. Pecan is called at line 90;
`algorithm_ready_seconds` is recorded at line 91. The full result is written
at line 96; `end_to_end_seconds` is recorded at line 97. Server startup and
subsequent correctness verification are outside those timers. Pecan's internal
input snapshots, validation actions and intermediate checkpoints are inside.

## What the 33.05 GiB number measures

The run used one source, 16,777,216 vertices, 268,435,456 input edge tuples,
undirected execution, DeltaStar with delta 0.1, two worker processes and 32
partitions. It converged in 60 rounds.

**33.05 GiB is the whole-container lifetime cgroup peak**, including all
container processes, charged page cache and correctness verification.
Sampled process PSS peaked at **20.24 GiB during execution** and **26.64 GiB
during verification**. These are different measurement boundaries; none is a
measurement of the frontier alone, and their difference is not an allocation
breakdown. The host was shared, so recorded durations are diagnostic observations.

Evidence: [closed measurement review](https://github.com/querygraph/grust/blob/6bdd55748fa0e9233a051d52c6b0965786947676/docs/reviews/sail-stream-experiments-2026-09-30/logging03-closed-review/README.md)
and [completed physical-output check](https://github.com/querygraph/grust/blob/6bdd55748fa0e9233a051d52c6b0965786947676/docs/reviews/sail-stream-experiments-2026-09-30/COMPACT-REPLAY-AND-SSSP.md).

## Why `compact_struct_min.rs` exists

Pecan selects the best label for each vertex with ordinary
`groupBy("id").agg(min(struct("distance", "hops", "parent")))`. Distance is
compared first, then hop count, then parent ID. This keeps ties deterministic.

The [Rust file](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-function/src/aggregate/compact_struct_min.rs)
is an optimization we added to the Sail fork's SQL engine. For the exact
`Struct<Float64, Int64, Int64>` shape, it replaces the original DataFusion
accumulator's separately owned singleton Arrow structures with a 32-byte inline
record per group. It preserves the original comparison and null behavior.
It also removes the original accumulator's repeated scan over all resident
groups on each input batch.

In the isolated 100,000-group allocation test, retained requested memory was
204,831,488 bytes for the original accumulator and 4,194,304 bytes for the
compact one (the vector had capacity for 131,072 groups). This excludes the
graph, joins, group keys and the rest of the query. The
[allocation report](https://github.com/querygraph/grust/blob/6bdd55748fa0e9233a051d52c6b0965786947676/docs/reviews/sail-stream-experiments-2026-09-30/STRUCT-MIN-ALLOCATION.md)
contains the source analysis, controls and limits. The reported scale-24 run
used this modified Sail runtime; it is not a stock-Sail measurement.

## UNION versus EXPLODE/UNNEST review targets

There are two distinct rewrites to test: direct/reverse edge expansion in
`traversal.py`, and reached-state/candidate merging in `traversal_stepping.py`
and the reference/frontier loop in `traversal.py`.
The latter is not a mechanical substitution of one operator: an equivalent
EXPLODE formulation may change joins and duplicate intermediate self labels.
Compare exact results and physical plans before comparing time and memory.
The focused comparison is being prepared; this document does not claim results
for it or infer Spark behavior from a DataFusion run.
