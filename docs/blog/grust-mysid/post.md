# Grust Mysid: twenty-three graph algorithms, and the properties they needed

Grust gives Rust applications one property-graph API across memory, embedded databases, SQL systems and remote graph services. Nodes, edges, typed identities, traversals, mutations, schema and graph algorithms are written once against that API; Memory, Sail/Spark, PostgreSQL, pgGraph, PostgreSQL SQL/PGQ, Turso, SurrealDB, FalkorDB, LanceDB and CocoIndex sit behind it, and each adapter states which operations it pushes down, runs natively, answers through the portable reference, or does not support. `grust-cypher` is the portable GQL/Cypher layer over the same model. Mysid 0.22.0 is about what those graphs can now be asked.

See the [repository and API guide](https://github.com/querygraph/grust), the [Grust book](https://firstpair.org/read/grust/), the [GQL profile statement](https://github.com/querygraph/grust/blob/main/docs/GQL_PROFILE_STATEMENT.md) and the full [`CHANGELOG.md`](https://github.com/querygraph/grust/blob/main/CHANGELOG.md).

## Ten kernels became thirty-three

Tadpole shipped ten graph algorithms. Mysid registers thirty-three, and every one is reachable the same three ways: as a Rust function over a projection, as `CALL grust.algorithms.<name>(...)` in Cypher, and as typed Arrow batches for an embedder that holds its own graph.

The additions group into four families. **Community detection**: Louvain, Leiden, label propagation, and `modularity` to score a partition somebody else produced. **Centrality**: betweenness with optional sampling, closeness, harmonic, eigenvector, Katz, and HITS. **Structure**: k-core, triangle counting, local clustering coefficient, node similarity, bridges, articulation points, biconnected components, and minimum or maximum spanning forests. **Paths and flow**: Bellman–Ford, A\*, maximum flow and minimum cut. Plus FastRP, which produces an embedding per node rather than a number.

Several of these carry decisions worth stating rather than discovering.

**Leiden guarantees what Louvain does not.** Louvain can leave a community in two disconnected pieces: a node that held it together moves away and nothing looks back. Leiden refines each community before coarsening, so every community it returns is connected — weakly connected, on a directed projection. The refinement here is greedy rather than randomised, which keeps runs reproducible and gives up the paper's asymptotic optimality guarantee. That trade is stated in the kernel's documentation, not hidden in it.

**Bellman–Ford treats a negative cycle as a result, not an error.** If one is reachable from the source, no distance beyond it is a minimum — every lap lowers it. So the kernel withholds distances and returns the cycle itself as a witness the caller can check: the arcs exist and their weights sum below zero. An undirected edge of negative weight is a negative cycle of two arcs and is reported as one.

**A\* cannot check the one thing that would make it wrong.** Its heuristic must never exceed the true remaining cost. Given that, it returns exactly what Dijkstra returns, which is how it is tested. Overestimate and it returns a real path that is not the shortest, and no kernel can tell the difference between an optimistic estimate and a genuinely expensive graph. The registered procedure's heuristic is great-circle distance from two coordinate properties, which is admissible only where the weights are distances in metres — the same metres against weights in seconds is not a lower bound, and is the usual way this goes wrong.

## Node properties, and why they are not part of the projection

Most of the remaining catalog needs something per node that is not topology: a community to score, a coordinate to steer by, a vector to compare. A projection carried one edge weight and nothing else.

Mysid adds `NodeProperties`: typed columns read per projected node, from a `Graph` or from Arrow node batches. Four kinds — `Number`, `Integer`, `Vector` of fixed-length `f32`, and `Category` for dictionary-encoded strings usable in equality filters only.

They are a *sibling* of the projection rather than a field on it. A projection is expensive to build and is cached; which property columns a call wants varies per call. Keeping them apart means changing a column never rebuilds topology. It also means row alignment is a fact rather than a convention: a `NodeProperties` is built against a projection and holds it, so it cannot be paired with the wrong one.

A missing value is an error naming the node, unless the caller asks for a default or to keep nulls — and a column read keeping nulls is reachable only through the `optional_*` accessors, so a kernel that did not ask for nulls cannot forget to handle one. A silent zero inside a feature vector is a wrong answer that looks like a right one.

## Threads come from the execution, and the results do not change

`grust-algorithms` gained a `parallel` feature, and `degree`, `pagerank`, `bfs`, `multiSourceBfs`, `wcc` and the new per-source kernels use it.

The contract is stricter than "it is faster". A kernel's result is bit-identical at any worker count, including its floating-point residuals and its charged work — each parallel kernel is tested at one, two, three and eight workers and compared bit for bit. That is achieved by cutting work into partitions the input determines rather than the worker count determines, and combining partial results in index order. Fixed partitions wherever a float sum is formed; width-dependent partitions only where workers write disjoint slots.

**Threads are requested, never assumed.** `ExecutionContext::with_concurrency` is how a caller asks; an execution that asks for nothing runs single-threaded and starts no pool. That matters for an embedder inside a query engine that already owns a runtime and a thread pool of its own, and it means upgrading to Mysid does not silently fan a query out across every core.

Below a measured floor a kernel stays sequential, because a pool costs more than it saves on small inputs. Those floors are measurements, not taste, and two of them are separate constants because the crossovers genuinely differ.

## Accounting without the lock

Cooperative budgets are how an untrusted or shared caller can be given an algorithm without being given the machine: work is charged as it is performed, memory is admitted before it is allocated, and cancellation and an optional deadline are observed during execution, with an exhausted budget failing exactly at its limit.

In Mysid the memory counters join the work counter as atomics, admitted through the same compare-exchange. The reference Cypher executor charges the logical bytes of every copied value, so a streaming query charged memory once or more per element and took a lock each time; on a full-path `reduce` query over a 4,096-node chain that was about 13% of the run.

Work charging also moved to a per-worker meter that draws from the shared budget in blocks. On one laptop, over a million-node graph, the sequential kernels gained between 16% and 40%. Those are single-host figures, and the paired benchmark harness — which runs each variant against a C++ reference and validates every sample — measured the same change at 17% on three of four graph families and a 4% regression on the fourth. Both numbers are in the record; the harness is the one to quote.

Three behaviours changed and are worth reading before upgrading: `usage()` reads its figures in sequence rather than as one snapshot, so exact totals should be read after execution; a peak can trail a charge by an instant but never misses a completed one; and a poisoned lock can no longer fail a memory charge.

## What is not here

**No Cypher surface changed.** The algorithms are procedures, and `grust-cypher`'s language profile is what it was in Tadpole.

**Live backends were not re-qualified.** These kernels run over a projection built from a snapshot, so no backend planner is involved, and no backend was re-tested for this release.

**`articleRank` is finished but not shipped.** It conflicted with a PageRank repair that landed after it, and resolving that conflict requires a decision about its divisor on the unweighted path rather than a textual merge. It will follow rather than be guessed at.

**The parallel kernels are measured, not tuned.** The floors come from one machine; the crossover on yours will differ, and a kernel that measures 1.0x there is a kernel with no parallel implementation rather than a kernel that failed to gain.

## Upgrading

Mysid is a lockstep release: move every direct Grust crate dependency to 0.22.0 together. `WeightSelection` gains a variant for projections that admit negative weights, so code matching it exhaustively needs one more arm; nothing is signed unless a caller asks. Everything else is additive.
