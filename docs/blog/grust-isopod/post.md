# Grust Isopod: typed Cypher execution on shared Arrow graphs

Grust gives Rust applications one property-graph API across memory, embedded
storage, SQL systems and remote graph services. Applications retain stable graph
identities and reusable algorithms while choosing backend capabilities explicitly.
Isopod 0.17.0 extends that architecture with a typed Cypher execution bridge over
shared Arrow graph snapshots, alongside the existing Rust kernels and adapters.

## From Cypher text to native execution

Combine facade features `cypher` and `datafusion` to access
`grust::datafusion::cypher`. `GraphSnapshot::execute` accepts Cypher text and
parameters, uses the existing parser and semantic analyzer, builds DataFusion 55
logical plans, and returns ordinary Cypher rows under explicit output limits.
It generates no SQL text and makes no intermediate row-oriented graph.

The supported surface includes node scans and fixed-length paths, incoming and
outgoing edges, undirected matching, repeated and anonymous nodes, scalar property
maps and predicates, grouping, count variants, integer/string extrema, DISTINCT,
ordering and pagination. Shared expression and RETURN compilers keep these rules
consistent across pattern shapes. Portable integer comparisons now retain exact
Int64 ordering beyond floating-point integer precision.

## Identity and resource boundaries

Validated native Arrow tables retain their buffers across snapshot capture.
Physical edge ordinals distinguish parallel edges even when external IDs are
missing or repeated. Trail composition excludes physical edge reuse and rejects
plans from different snapshots. Undirected matching emits both non-loop
orientations and one row per self-loop.

Native Arrow consumers can retain result batches and compose them with the
existing Arrow/ADBC readers. Portable consumers receive exact scalar rows;
incremental collection checks cumulative row counts and serialized JSON bytes
without building a JSON buffer. Errors propagate without silently retrying
another executor or snapshot.

This release explicitly selects DataFusion. Automatic cost-based routing,
complete Cypher read-policy admission, variable-length paths, OPTIONAL MATCH,
and broader scalar/aggregate mappings remain active work. Output limits do not
replace candidate-work, intermediate-memory, input or deadline contracts.

## Measurements with their boundaries

Pinned scan and path profiles retain independent answer checks, preparation
costs, errors and resource boundaries. All 84 parallel-ring path checks passed.
At 100,000 nodes, three-trial prepared two-hop medians were 0.248 seconds indexed
and 0.019 seconds typed DataFusion; three-hop medians were 0.461 and 0.034 seconds.
Arrow preparation added approximately 0.068–0.069 seconds. Indexed execution was
faster on the 17-node fixtures. Different admission boundaries are disclosed;
these measurements do not establish a universal routing threshold or backend
performance parity.

See the [repository documentation](https://github.com/querygraph/grust), the
[Arrow pipeline chapter](https://github.com/querygraph/grust/blob/main/docs/book/chapters/arrow-pipelines.md),
the [path receipts](https://github.com/querygraph/grust/tree/main/benchmarks/arrow-pipelines/evidence/cypher-paths-100822f),
and the [Grust book](https://firstpair.org/book/grust) for contracts and evidence.
