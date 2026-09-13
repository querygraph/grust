# Grust 0.14.0 “Acorn”: Graph Algorithms Across Rust, Arrow and Cypher

Grust is a backend-neutral property-graph library for Rust. Its shared API describes labeled nodes, relationships, properties, schemas, traversal and mutation across Memory, Turso, PostgreSQL, FalkorDB, SurrealDB, Sail, LanceDB and other adapters. Acorn adds reusable graph analytics to that foundation: applications can capture an authorized immutable graph, prepare its topology once, and consume the same Rust algorithms through typed Rust results, Arrow batches or ordinary Cypher procedures.

The [repository guide](https://github.com/querygraph/grust), [analytics contract](https://github.com/querygraph/grust/blob/main/docs/GENERALIZED_ALGORITHMS.md) and [Grust book](https://firstpair.org/read/grust/) explain the complete surface. The rebuilt book is also available in the repository’s [versioned artifacts](https://github.com/querygraph/grust/tree/main/docs/book/build/dist).

## One implementation, several consumers

The initial catalog includes breadth-first search, multi-source BFS, depth-first traversal, Dijkstra distances, full shortest paths, weak and strong components, weighted PageRank, and topological sorting with concrete cycle witnesses. Projection statistics and a scoped CSR buffer estimate help applications inspect the selected topology. The estimate explicitly excludes input storage, ID maps, kernel scratch and output; it is not a total-memory promise.

Direct Rust callers work with packed adjacency, external node IDs and typed results. Arrow input reads structural columns from multiple batches without constructing a property graph first. Arrow output provides bounded typed batches, including full paths, while retaining the memory reservation that owns their storage.

Cypher connects through an extensible registry:

```cypher
CALL grust.algorithms.dijkstra('start', {weightProperty: 'cost'})
YIELD nodeId, distance
RETURN nodeId, distance
```

Applications register the providers they need. Signatures describe arguments, configuration, output columns, permissions and streaming behavior; validation, prepared explanations and `db.procedures` use that metadata. An independent provider can join the registry without modifying the parser or adding a procedure-name branch to the executor. Prepared plans retain their registry generation.

## Full paths have real costs

A full-path result contains every node and cumulative cost on each selected path. On a directed chain of 65,536 nodes, those arrays contain 2,147,516,416 entries apiece. Returning only distances would measure different work.

Acorn streams CALL, YIELD, filtering, simple WITH, UNWIND and ungrouped COUNT/SUM/AVG through bounded consumers. Generic typed-array aggregation visits the actual entries while avoiding a cloned binding for every element. Direct Rust can consume borrowed path visits; Cypher builds and admits each owned path row. Blocking operations retain their disclosed materialization boundary, and oversized individual rows can fail admission.

Memory, work, cancellation and deadline checks share one execution context. Retained projections, kernel scratch and output batches keep their reservations alive. This is cooperative allocation accounting, not a process-memory sandbox. Caller-owned snapshots and a returned legacy result table remain the caller’s responsibility.

## Snapshot and backend boundaries stay explicit

Projection reuse is scoped to one query and keyed by graph, revision, principal and projection options. Identity strings do not grant access: a trusted adapter must capture and authorize the snapshot first. The same bounded prepared query is tested against independently captured Memory and private Turso snapshots, including captures that remain unchanged after later writes. This demonstrates local analytics over those snapshots; it does not claim native algorithm execution in every backend.

Acorn also integrates backend maintenance work. Surreal and Helix HTTP distinguish bulk-load batches from incremental writes. LanceDB reuses table handles while checking current table state and serializing local recreation; tests cover writes through another connection and recreation races. Turso retires its optional sync snapshot cache before a pull can change local state, including failed or cancelled pulls. Turso now keeps parallel edges that carry distinct ids, as Memory and LanceDB do, and rebuilds a database created with the older edge key once, in place. Under MVCC it commits a whole-graph load in groups instead of one transaction.

Memory stores each edge once, as a 16-byte record with interned ids, and Cypher reads that store in place instead of a copy of the graph. Loading 10 million untyped edges and answering indexed reads over them peaks at about 96 bytes per edge instead of 222.

## Evidence and limits

The Acorn workspace checks report 1,486 passing tests and 47 explicitly ignored tests. The algorithm oracle exhausts every directed three-node topology in all three orientations; weighted tests use an independent shortest-path oracle. Docker image validation checks 72 upstream participant cases against the retained C++ implementation. The [benchmark receipts](https://github.com/querygraph/grust/tree/main/benchmarks/algorithms) distinguish correctness, failures, resource envelopes and timer boundaries, and retain historical participants and official GDS calls.

The supported catalog is finite. Arbitrary Cypher, distributed execution, negative-weight shortest paths and the broader GDS catalog remain outside this release’s contract. The registry, projection and result interfaces provide the extension points for subsequent algorithms without requiring a second execution engine.
