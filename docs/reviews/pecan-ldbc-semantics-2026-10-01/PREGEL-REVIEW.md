# Shared Pregel primitive: source review

Reviewed 2026-10-01. Scope: Sem's proposal to share PR, SSSP and multi-source traversal machinery, reduce actions, and combine active-adjacency joins with aggregation. This is a source review and engineering proposal, not a performance result. No source code, frozen correctness helper or running test was changed.

The referenced screenshot `~/icloud/src/grust/1790880338551.png` was unavailable on Morrobay and was not read. The supplied text is sufficient for the proposal reviewed here.

## Source identities

- Pecan controller: [`querygraph/sail@6ae2e43a903c2cee02da170465c922c72b76198e`](https://github.com/querygraph/sail/tree/6ae2e43a903c2cee02da170465c922c72b76198e).
- Existing runtime binary: source `56194b170155301ba91077f0ba3df31fe2c78b6b`, SHA-256 `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`. Controller source inspection does not establish a newly rebuilt runtime.
- Sem source: [`SemyonSinchenko/graphframes-rs@b4da56dabe20bba8e29563e06acc5179b2113ce3`](https://github.com/SemyonSinchenko/graphframes-rs/tree/b4da56dabe20bba8e29563e06acc5179b2113ce3).

Pecan was inspected through the frozen guest checkout `/targets/pecan-typed-tests-20261001/candidate`. The correctness harness separately checks a clean controller commit, source-first package origins, runtime/native binary hashes, dependency versions and input-member hashes. This document does not substitute for its execution receipts or their closure audit.

## The proposed expansion already exists

Pecan's [frontier traversal](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal.py#L52) selects the active relation, joins it to adjacency, projects destination messages, unions existing reached state and reduces with `min(struct(distance, hops, parent))` grouped by vertex ID. [DeltaStar](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal_stepping.py#L40) uses the same expansion/reduction for the minimum pending bucket.

Both build lazy expressions. Neither writes candidate edge messages to a separate Parquet generation each round. `unionByName` supplies existing labels as additional candidates; the subsequent aggregate selects the best label. Removing the union without replacing that state-preservation operation would lose previously reached vertices or labels.

The existing costs are:

| Operation | Frontier traversal | DeltaStar |
|---|---|---|
| Expansion | Active vertices joined to adjacency | Minimum-bucket vertices joined to adjacency |
| State update | Existing state union candidates, grouped lexicographic minimum | Same |
| State persistence | One updated-state materialization | One updated-state materialization |
| Activity/pending update | Join updated state to previous labels; materialize changed frontier | Same comparison; two anti joins remove processed/superseded pending labels; union changed labels; materialize pending |
| Controller scalar | `next_frontier.count()` | Minimum pending bucket aggregate at each expansion; emptiness check if the cap is reached |
| Ownership | Remove obsolete state/frontier generations | Remove obsolete state/pending generations |
| Final output | Full vertex left join retains unreachable vertices | Same |

These are source-level operations, not measured physical scans or exact transport counts. [StagingRun.materialize](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/staging.py#L40) also performs ownership checks, a checkpoint write, read-back and schema checking. Those boundaries must be included when measuring actions.

## What Sem's shared Pregel does

Sem's [Pregel source filtering and triplet join](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/pregel.rs#L383) pushes source participation before the adjacency join when destination state is unnecessary. Its [named-message construction](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/pregel.rs#L425) uses `union_by_name` for multiple message expressions.

The same loop [checkpoints aggregated messages](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/pregel.rs#L433), left joins them to state, checkpoints updated state, evicts old checkpoints and optionally counts voting vertices. Edges and state use sorted, partitioned checkpoints; aggregated messages use a separate checkpoint to reduce peak memory. A common abstraction therefore does not itself establish fewer actions or safe removal of those checkpoints.

Its [shortest-path builder](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/shortest_paths.rs#L150) creates one distance/message/aggregate per landmark, sends `distance + 1`, and uses Int32 maximum as unreachable. It drops edge weights. This pinned implementation computes hop distances, rather than weighted DOUBLE SSSP.

Its [PR builder](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L125) sends thresholded deltas and normalizes at the end. That recurrence must remain distinct from LDBC's uniform initialization, dangling redistribution and fixed-step power PR. Reuse of a message primitive need not imply reuse of those numerical semantics.

## Minimal shared primitive

Start with a typed functional plan builder:

```text
send_reduce(active: DataFrame, adjacency: DataFrame,
            spec: SendReduceSpec) -> DataFrame
```

`SendReduceSpec` should be an immutable typed record describing source projection, optional destination projection, message direction, named message expressions, destination key and named reducers. It produces a lazy relation and performs no collection, checkpoint, storage allocation or Python UDF execution.

Keep the following policies explicit around that primitive:

- **State update:** PR sum/restart/dangling equations; SSSP lexicographic distance/hops/parent minimum; preservation of inactive and unreachable vertices.
- **Activity and stopping:** fixed iteration count, changed frontier, pending bucket selection or PR residual target. These are different contracts.
- **Ownership:** allocation, successful checkpoint commitment, cancellation, uncertain writes, obsolete-generation removal and final result lease.
- **Certificates:** full fixed-point PR residual where required; traversal completion and parent/hop witnesses; independently retained output validation.

SSSP's lexicographic minimum permits reducing messages before merging them with retained state. That is a concrete plan variant to inspect, not a reason to bypass state preservation. PR reductions use DOUBLE arithmetic and require the chosen recurrence and numerical acceptance criteria to remain explicit.

For multi-source work, choose the output first. Distance to the nearest seeded source can keep one label per vertex; distances for each of `k` landmarks require up to `k` labels per vertex. Sem's current builder uses the latter representation. State size, message width, deterministic source/parent ties, direction and weighted semantics belong in admission and correctness contracts.

## Reducing actions and establishing physical effects

The next useful prototype is an owned checkpoint operation that returns bounded round statistics from the same committed write. Carrying activity with state, or emitting the next pending bucket alongside its checkpoint, could remove a separate frontier/count or bucket request. Checkpoint data and statistics must describe the same completed execution; missing statistics, uncertain writes and failures must not be interpreted as convergence. PR still needs its required global/dangling reductions and final certificate.

A lazy shared builder alone is a refactor. Establish action reduction through recorded ExecutePlan requests, writes, scalar reductions and ownership operations. Preserve the same output, stopping rule, memory envelope and failure behavior when comparing a plan variant.

Before claiming fusion, fewer edge reads or lower memory, retain physical plans and operator evidence for:

- Join implementation, build side, partitioning and any inserted exchange/sort.
- Whether union branches repeat adjacency scans or expansion work.
- Aggregate cardinality estimates versus observed rows; rows/bytes read and written.
- Peak participating memory and spill, including whether an aggregate checkpoint prevents overlapping large operators.

An active relational join can still scan the full adjacency relation. Streaming join output into aggregation can avoid an intermediate write while retaining substantial hash state or repartition work. Logical `join`/`groupBy` composition and `unionByName` do not establish either physical property by themselves.

Recommended order: finish official tiny-graph qualification; extract the typed lazy primitive without changing actions; then measure one explicit state/metrics commitment variant with retained plans and unchanged semantic checks. Keep the pending-bucket schedule as a distinct traversal policy.
