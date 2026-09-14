# Grust Copepod: shared graph bindings, exact empty sums

Grust gives Rust applications one backend-neutral property-graph API across memory, embedded databases, SQL systems and remote graph services. Nodes, relationships and properties keep the same core contracts while adapters express their native storage and query capabilities. Copepod, version 0.15.1, improves the shared Cypher executor used for portable graph reads and corrects an aggregate compatibility gap. The Arrow, ADBC and optional DataFusion 55 foundations remain available without becoming requirements for ordinary graph applications.

## Immutable bindings across candidate rows

A relationship match expands a candidate into further candidates. Previously, each copy cloned every bound node and edge, including their property maps. CPU sampling of a graph-shaped relational workload showed substantial time in row copying and allocation, followed by disposal of candidates rejected by the filter.

Copepod shares immutable node and edge bindings across those copies. Projected values remain owned, physical relationship-slot identity remains intact, and row order is preserved. The executor retains conservative logical full-element copy charges even when the underlying storage is shared. This changes data movement without introducing another query language, a backend-specific shortcut or unsafe code.

On the disclosed 20,000-node fixture, three-trial median two-hop Cypher time changed from 4.00 seconds to 2.34 seconds. Whole-process peak RSS changed from 10.50 GB to 6.03 GB. Those are descriptive measurements on one local workload: both query engines, graph representations and allocator state coexist in the process. They are not isolated per-engine memory figures or a universal speed guarantee. Every trial, source revision, binary hash, error and independent oracle is retained in the [qualification evidence](https://github.com/querygraph/grust/tree/main/benchmarks/arrow-pipelines/evidence).

The full MATCH pipeline still materializes candidates. Sharing reduces repeated copying; it does not make that pipeline fully streaming or establish a whole-process memory cap. The explicit DataFusion SQL profiles continue to disclose a separate execution class, and automatic Cypher lowering is not supplied by this change.

## The identity of an empty sum

Independent fixtures exposed another issue: Cypher returned null for an empty sum. Copepod returns integer zero for empty and null-only numeric sums in both materialized and streaming aggregation. DISTINCT sums follow the same rule. Average remains null with no numeric input, and a grouped query with no input still produces no groups.

Regression coverage includes missing properties, empty matches, null-only inputs, DISTINCT, grouping, owned and indexed reads, and mutation RETURNING through the shared projection layer. All 54 optimized fixture checks passed after the correction; the original mismatches remain in the evidence rather than being rewritten as successes.

## Measured increments in a shared architecture

These changes build on Grust's native Arrow pipelines, ADBC composition and DataFusion 55 execution foundation. Relational profiles make conversion, registration, execution and result-consumption boundaries visible, while direct graph algorithms retain their own kernel and resource contracts. Broader loading performance, algorithm coverage and language compatibility remain active engineering work.

See the [repository documentation](https://github.com/querygraph/grust), [Arrow and ADBC architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), [compatibility inventory](https://github.com/querygraph/grust/blob/main/docs/goals/cypher-algorithm-compatibility.md), and [Grust book](https://firstpair.org/book/grust) for the public contracts and remaining boundaries.
