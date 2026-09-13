# Grust Algorithm Procedures

Registry adapters for the same nine algorithms exposed by `grust-algorithms`.
Register them with `register_algorithms(&mut builder)`, build an immutable
registry, and pass it to Grust Cypher's ordinary registry query API. The facade's
optional `algorithms` feature reexports the kernels and this adapter crate.

```cypher
CALL grust.algorithms.dijkstra('source-id', {weightProperty: 'cost'})
YIELD nodeId, distance
RETURN nodeId, distance
```

| Procedure suffix | Arguments | Outputs |
| --- | --- | --- |
| `bfs` | source ID, optional configuration | nodeId, distance |
| `dijkstra` | source ID, optional configuration | nodeId, distance |
| `shortestPaths` | source ID, optional configuration | sourceNodeId, targetNodeId, totalCost, nodeIds, costs, edgeOrdinals |
| `wcc`, `scc` | optional configuration | nodeId, componentId |
| `pagerank` | optional configuration | nodeId, score, iterations, converged, residual |
| `dfs` | source ID, optional configuration | nodeId, visitIndex |
| `multiSourceBfs` | nonempty source ID array, optional configuration | nodeId, distance |
| `topologicalSort` | optional configuration | acyclic, nodeIds, cycleNodeIds |
| `projectionStats` | optional configuration | nodes, edges, arcs, selfLoops, csrBytes |
| `estimateCsr` | optional configuration | nodesUpperBound, edgesUpperBound, maxArcs, outgoingCsrBytes, reverseCsrBytes, positionsBytes |

Names have the `grust.algorithms.` prefix and resolve without ASCII case
sensitivity. Node IDs are external strings; component IDs are the external ID
at the component's minimum projection row. Unreachable distances are null.
Full paths omit unreachable nodes and include the zero-hop source. Original
edge ordinals disambiguate parallel edges even when external edge IDs repeat.

Common configuration keys are `orientation` (`outgoing`, `incoming`, or
`undirected`), nullable `nodeLabels` and `relationshipTypes` string arrays,
nullable `weightProperty`, and nullable numeric `defaultWeight`. Null label
selection includes all labels; an empty array selects none. A default weight
requires a property. Missing/null weights otherwise fail. BFS ignores weights.
PageRank additionally accepts `damping`, `tolerance`, `maxIterations`, and nullable
floating-point array `personalization`; kernel defaults and semantics are
documented in `grust-algorithms`.

Providers require an adapter-authorized immutable local snapshot. The bounded
query API additionally requires `allow_read_procedures`; catalog permission alone
does not admit analytics. Read/stream and projection inspection are implemented. `estimateCsr` sizes only
packed adjacency buffers using whole-snapshot counts, conservatively ignoring
selection. It excludes graph storage, ID maps, original edge mappings, kernel
scratch, outputs and allocator overhead; it is not total memory admission.
Mutation, write-back, native remote execution and spilling are not implemented.

The general Cypher executor incrementally consumes CALL/YIELD filters, simple
WITH, UNWIND, ordinary RETURN and ungrouped COUNT/SUM/AVG. LIMIT propagates early
termination on the incremental path. Blocking or other unsupported streaming
shapes use the existing materializing executor and its budget. Scalar providers
currently return one row per batch; full paths use one owned array row per path.
Typed array/index aggregate fusion consumes every actual array element without
per-entry binding clones. Query-scoped preparation reuse includes graph, revision,
principal and all projection options; correlated kernels still run per input row.
`db.procedures` (from `register_builtins`) and prepared-query `explain()` use the
same pinned definitions as execution. Snapshot explanations additionally identify
the revision and principal without invoking providers.

`examples/full_path_receipt.rs` consumes actual node and cost entries through
direct Rust or ordinary Cypher, then checks independent count/checksum formulas.
Its local receipts do not reuse historical benchmark timings or claim backend
protocol parity. See the repository's `docs/GENERALIZED_ALGORITHMS.md` tracker.
