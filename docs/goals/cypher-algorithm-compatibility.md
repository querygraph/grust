# Cypher and graph algorithm compatibility inventory

Inventory revision: 1, reviewed 2026-09-14. Status: active qualification.
This tracks the compatibility part of the
[engineering goal](arrow-performance-parity.md). An implemented Grust feature
is not automatically equivalent to a similarly named reference feature.

## Reference boundaries

The language reference is [Cypher 25](https://neo4j.com/docs/cypher-manual/25/queries/).
The GDS manual retrieved on the review date identifies itself as
[2026.08](https://neo4j.com/docs/graph-data-science/current/).
These documentation references establish the inventory, not an executed test
configuration. Every differential run must additionally record the exact Neo4j
and GDS artifacts, edition, enabled language version and configuration. The
`current` documentation route can change; refresh the inventory deliberately.
Existing benchmark artifacts remain tied to their original versions.

Grust's [scoped GQL profile](../GQL_PROFILE_STATEMENT.md) and
[algorithm catalog](../GENERALIZED_ALGORITHMS.md) remain authoritative for its
implemented surface. This inventory does not rename those contracts or equate
an internal GQL profile with complete Cypher 25 compatibility.

## Language qualification

| Area | Existing Grust evidence | Remaining compatibility work |
| --- | --- | --- |
| Matching, filters, projection, aggregates | GQL feature manifest and portable-read corpus | Differential null/missing, numeric conversion, multiplicity and ordering cases against the pinned reference |
| Paths and shortest-path matching | Scoped single-segment simple-path implementation | Map reference path modes and selectors individually; retain unsupported cases |
| Query composition and subqueries | Existing UNION and correlated import-all subquery tests | Explicit Cypher 25 scope, conditional and sequential composition inventory; no inference from similar syntax |
| Writes and identity | Strict-write golden corpus and mutation backend contracts | Record generated/explicit identity differences, matched cardinality and transaction boundaries |
| Types and functions | Grust Value types and expression tests | Function-by-function coercion, precision, temporal and error equivalence |
| Procedures | Extensible registry, correlated CALL, checked cursors and admission tests | Signature, option, result schema and error mapping; no nominal GDS aliases |
| DDL, indexes and transactions | Capability-reported metadata and transactional stores | Separate metadata acceptance from physical indexes, isolation and durable effects |
| Explain and resource reporting | Typed prepared-query explain and execution accounting | Distinguish typed API from Cypher EXPLAIN/PROFILE syntax and engine-specific metrics |

Use `grust_cypher::gql::feature_manifest` and the existing corpora as inputs;
do not create a competing list of boolean capability claims. A compatibility
case needs query text, parameters, initial graph, expected values or error,
execution class, backend, reference version and source-pinned receipt. Keep
semantic mismatch, unsupported, unavailable and resource failure distinct.

## Algorithm qualification

The reference [algorithm taxonomy](https://neo4j.com/docs/graph-data-science/current/algorithms/)
includes path finding, centrality, communities, similarity, DAG operations,
embeddings and link prediction. Individual functions require individual
contracts; a family row below is not a claim of complete family coverage.

| Family | Implemented Grust operations | Outstanding work |
| --- | --- | --- |
| Reachability and paths | BFS, DFS, multi-source BFS, Dijkstra, one selected shortest path per reachable target | Reference option/result mapping; A*, negative weights/cycles, all-pairs and k-shortest contracts |
| Components and DAGs | WCC, SCC, topological sort with cycle witness | Component-label equivalence, orientation and loop/multigraph cases; additional DAG operations |
| Centrality | Weighted PageRank with personalization and convergence reporting | Reference normalization/dangling/tolerance mapping; degree, closeness, harmonic, betweenness, eigenvector and HITS |
| Structural analytics | Projection statistics and CSR estimates | Triangle, clustering, k-core, bridge and bipartite contracts with exhaustive small-graph oracles |
| Communities and similarity | No catalog implementation claimed | Seeded convergence/objective contracts and bounded candidate-pair execution |
| Forests, flow and cut | No catalog implementation claimed | Capacity, direction, disconnection and independent optimality checks |
| Embeddings and learning | No catalog implementation claimed | Explicit model lifecycle, training provenance, resource limits and validation |

GDS [execution modes](https://neo4j.com/docs/graph-data-science/current/common-usage/running-algos/)
are separate dimensions. Grust currently provides read-only local projection
and direct Rust/Arrow results. Backend-native execution, graph mutation and
persistent result writing are not supplied by that executor. DataFusion's
relational spill support does not imply that graph kernels can spill.

## Execution and performance evidence

For each admitted job, record capture, projection, preparation, kernel execution,
result consumption and write-back separately when those phases exist. Compare
only equal datasets, semantics, protocols, resource envelopes and execution
classes. Report retained input and caller allocations outside query budgets.

New DataFusion 55 paths need independent semantics before selection and measured
end-to-end costs after selection. Native database pushdown, local relational
execution and packed graph kernels are separate execution classes. A fast batch
microbenchmark does not qualify database loading or an algorithm query.

Completion requires replacing outstanding rows with specific tested contracts
and linked receipts, retaining every failure. Neither the Arrow foundation
release nor this initial inventory closes the wider goal.
