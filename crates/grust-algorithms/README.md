# Grust Algorithms

Immutable selected property-graph topology and budgeted Rust graph kernels.
The repository's `docs/GENERALIZED_ALGORITHMS.md` tracks implemented capabilities,
unsupported modes and qualification evidence.

The direct Rust API provides BFS, Dijkstra distances, one full shortest path per
reachable node, weak and strong components, weighted PageRank, DFS, multi-source BFS and
topological order with a concrete cycle witness. Projections
retain node IDs and original edge ordinals, including isolates and parallel
edges. Directed orientation is explicit; weak components ignore direction.
Components use the minimum projection node row as their canonical label.

Build a projection with `GraphProjection::from_graph`, `from_topology`, or the
optional `arrow` feature's `from_arrow_batches`. Arrow ingestion reads typed
columns directly, including across multiple batches, without converting them
to Grust `Value` or property maps. Result `into_arrow_results` methods provide
bounded typed Arrow batches with retained admission. Full paths use LargeList
arrays; ordinals and iteration counts use UInt64. The companion
`grust-algorithm-procedures` crate registers these operations for ordinary Cypher.

Every projection takes a nonempty graph/revision/principal identity asserted by
the trusted adapter. This identity describes an admitted snapshot; constructing
it does not grant access to a backend. The caller admits its input graph or
Arrow buffers. Projection storage, working buffers and results share one
`ExecutionContext` for memory, work, cancellation and deadline enforcement.
Accounted bytes describe admission, not allocator overhead or process RSS.

Weights must be finite and nonnegative. Property integer weights are restricted
to the consecutive exact f64 domain `0..=2^53`. Missing and null weights either
fail or use an explicitly selected default. Unit projections omit weights.
Dijkstra reports reachable cost overflow as a numerical error. Unreachable
distances are positive infinity. BFS ignores projected weights.

`shortest_paths(...).visit_paths(...)` reuses path buffers and supports early
termination through `ControlFlow`. Each callback receives source-first node
rows, cumulative costs, and original edge slots. The source's zero-hop path is
included, and unreachable nodes are omitted. Copying or retaining callback data
requires consumer admission. `into_cursor()` supplies the same reconstruction
through a demand-driven borrowed path view. Kernel results share immutable
projection ownership, so dropping the caller's projection cannot invalidate IDs.

PageRank defaults to damping 0.85, L1 tolerance 1e-8 and 1000 iterations. Scores
start uniformly; teleportation and dangling mass use normalized personalization
or a uniform distribution. Zero outgoing weight is dangling. Results expose
iteration count, residual and convergence status; reaching the iteration limit
does not imply convergence.

`statistics()` inspects selected topology without running a kernel.
`CsrEstimate::upper_bound` sizes packed outgoing/reverse buffers and temporary
insertion positions. It excludes the graph, IDs, edge table, kernel/result memory
and allocator overhead; it must not be used as a total admission estimate.
