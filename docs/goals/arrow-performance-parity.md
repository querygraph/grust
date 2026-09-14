# Loading, algorithms, Arrow and compatibility

Status: active, requested 2026-09-14. This extends the delivered generalized
algorithms architecture; it is not a claim of universal feature or performance
parity. Existing benchmark runs retain their original source pins.

## Engineering objectives

1. Shared, extensible Arrow pipelines in every Arrow-based adapter, composable
   with standard ADBC readers and driver APIs. Preserve native buffers where
   schemas allow it; expose unavoidable encoding and materialization explicitly.
2. Efficient bulk loading, with documented upsert identity, batch admission,
   transaction boundaries and recovery behavior.
3. Fast direct Rust and ordinary Cypher graph algorithms with identical kernel
   semantics, exact independent oracles and retained resource accounting.
4. A versioned compatibility inventory against Neo4j's documented Cypher and
   graph-analytics capabilities. Close gaps through the existing registry and
   planner rather than query-text special cases or nominal aliases.
5. Reproducible, neutral measurements on the same datasets, protocols and resource
   envelopes. Keep pass, mismatch, unsupported, unavailable, error, timeout and
   not-applicable outcomes distinct. Host profiles and execution classes do not
   get pooled into a single performance claim.

## Current work

The shared Arrow and DataFusion 55 foundations are in implementation and qualification. See
[Arrow pipelines](../arrow-pipelines.md). Coverage includes native Arrow 55/58/59,
ADBC statement binding, C Stream export, multi-batch tables, columnar graph
validation, native adapter reader paths and explicit memory/copy boundaries.

The delivered algorithm inventory and unsupported modes remain in
[generalized algorithms](../GENERALIZED_ALGORITHMS.md). That inventory is the
starting point for catalog expansion, not evidence of complete Neo4j GDS parity.
The [Cypher and algorithm compatibility inventory](cypher-algorithm-compatibility.md)
tracks reference versions, remaining semantic qualification, backend execution
classes and required independent conformance evidence.

## DataFusion foundation and evaluation

User constraint: evaluate **DataFusion 55 only**. Do not select another
DataFusion release for a new integration. Verify its exact Arrow dependencies
and compatibility with each existing backend before changing dependencies.
This version constraint is separate from native Arrow SDK major versions.

DataFusion is already underneath Sail and LanceDB. First inspect and measure
existing scan/filter/projection and relational-operation pushdown. Implement a shared, optional DataFusion 55 foundation using native providers,
Arrow tables, upstream DataFrames and streams, explicit resources, and an ADBC
reader bridge. For in-process Arrow/Memory workloads, measure this relational execution layer for
large joins, aggregates, sorting and graph-input preparation. Keep direct packed
adjacency kernels as the baseline for traversal and iterative graph algorithms.

Candidates must be measured end-to-end: planning, data transfer, conversion,
projection, kernel execution and result consumption. No automatic speedup or
universal dependency is assumed. Preserve Cypher null, identity, multiplicity,
ordering and numeric semantics when lowering expressions to another engine.

References: [DataFusion architecture](https://datafusion.apache.org/user-guide/introduction.html),
[Sail query planning](https://docs.lakesail.com/sail/latest/concepts/query-planning/).

## Completion evidence

Each delivered increment requires focused correctness tests, applicable live
adapter tests, warnings-denied Rust checks, source-pinned optimized measurements,
updated user documentation, book artifacts and repository-required release
publication. Record qualified and unqualified boundaries explicitly. The overall
goal remains active while the compatibility inventory or required engineering
work is outstanding; a release of the Arrow increment alone does not close it.
