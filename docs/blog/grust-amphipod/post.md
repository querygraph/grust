# Grust Amphipod: degree analytics across Rust, Arrow and Cypher

Grust gives Rust applications a shared property-graph API across memory,
embedded databases, SQL systems and remote graph services. Backend adapters
retain their storage capabilities while reusable projections and algorithms
provide explicit identity, orientation and resource contracts. Amphipod 0.16.0
adds exact degree counts and optional weighted strength to this shared surface.

## One kernel, three interfaces

Direct Rust applications call `degree(&projection)`. Arrow consumers receive
bounded batches with external node IDs, UInt64 degree counts and nullable
Float64 strengths. Cypher applications call `grust.algorithms.degree` through
the ordinary procedure registry, with the same projection options and checked
integer results. The existing Arrow/ADBC and optional DataFusion 55 foundation
continues to support composition without requiring those dependencies for every
application.

Incoming, outgoing and undirected projections are supported. Isolates return
zero counts; parallel and zero-weight arcs count separately. Undirected loops
count once under Grust's projection contract. Unweighted strength is absent,
not an implicitly normalized score. Weighted strength requires finite
nonnegative weights and rejects overflow. Negative-weight policies and other
engines' loop conventions still require separate compatibility qualification.

## Measured work and retained resources

Unweighted degree reads existing CSR offsets in O(V). Weighted strength takes
O(V+A), without building a reverse index or copying the graph. Result buffers
retain memory admission. Bounded work-accounting chunks reduce synchronization
while maintaining cancellation polling and exact successful work charges.

On the disclosed prepared 65,536-node fixture, unweighted kernel estimates
changed from approximately 757 to 163 microseconds after batching admission;
weighted estimates changed from 6.23 milliseconds to 0.428 milliseconds.
These measurements include result allocation and disposal but exclude backend
capture, projection construction and Arrow output. They do not establish
end-to-end backend throughput. Raw samples, outliers, source pins, executable
hashes and qualification logs are retained in the
[degree evidence](https://github.com/querygraph/grust/tree/main/benchmarks/algorithms/evidence/degree-5d28f02).

Independent small-multigraph oracles cover all orientations, weights, loops,
parallel edges and isolates. Additional regressions cover memory admission,
work exhaustion, cancellation, overflow, chunk boundaries and both Arrow and
Cypher results. Broader centrality families and loading optimizations remain
active work.

See the [repository documentation](https://github.com/querygraph/grust),
[algorithm contracts](https://github.com/querygraph/grust/blob/main/docs/GENERALIZED_ALGORITHMS.md),
[compatibility inventory](https://github.com/querygraph/grust/blob/main/docs/goals/cypher-algorithm-compatibility.md)
and [Grust book](https://firstpair.org/book/grust) for details.
