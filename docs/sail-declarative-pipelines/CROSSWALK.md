# Spark SDP acceptance crosswalk

The pinned inventory has 462 static Scala test registration call sites, including
helpers and parameter declarations. It is not an expanded runtime denominator.
Assertion review currently covers 97 registrations; 365 remain unaudited. None
is fully qualified by executing the original Scala suite against Sail.

| Suite | Reviewed | Partial ports | Unmapped |
| --- | ---: | ---: | ---: |
| ViewSuite | 11 | 7 | 4 |
| MaterializeTablesSuite | 27 | 8 | 19 |
| SparkDeclarativePipelinesServerSuite | 19 | 14 | 5 |
| PipelinesHandlerSuite | 2 | 0 | 2 |
| SqlPipelineSuite | 38 | 29 | 9 |
| Total | 97 | 58 | 39 |

Each audited [inventory record](spark-4.2.1-inventory.json) identifies its phase,
covered/missing assertions and evidence. A partial behavioral Connect port does
not establish equivalence with Spark's internal graph objects or event assertions.
The 67 upstream Python executions and selected Sail regression counts do not
qualify the whole static inventory.

## Views and materialization

The [view audit](evidence/view-crosswalk/validation.json) covers all 11 source
registrations. Missing-input direct/downstream attribution, failed publication
without aliases, dependent SKIPPED events, stored view definitions and streaming
reads through persisted views remain open. Temporary-object rejection now has
structured metadata checks; streaming-query rejection metadata remains open.

The [materialization audit](evidence/materialization-crosswalk/validation.json)
covers all 27 registrations, including two explicit full-refresh boolean grids.
Its internal DatasetManager fixtures sometimes use batch queries with registered
tables that the Connect streaming-table API rejects; materialized-view ports
therefore qualify shared catalog assertions only. Internal empty materialization
must stay distinct from Connect's empty-pipeline rejection.

Outstanding catalog assertions include identity partition preservation/rejection,
exact refresh schemas, unknown properties, repeated nested-container materialization
and clustering metadata. General catalog behavior belongs in Sail, with LakeCat
one supported adapter for persistence/CAS/governance and capability coverage.

## Connect server and failure handlers

The [server audit](evidence/server-crosswalk/validation.json) covers 19 registration
sites. Exact output/flow identifier grids, missing-graph errors, once-option
validation, database capture, session ownership/coexisting outputs and deferred SQL
response shapes have partial ports. Internal registry counts/contents, retained
holder cleanup after close, mixed SQL/protocol graph metadata and original
streaming end-to-end fixtures remain unqualified. Deferred SQL response tests do
not qualify server enforcement of pipeline side-effect restrictions.

Both [failure-handler registrations](evidence/handler-crosswalk/validation.json)
are unmapped. One requires rethrowing an existing cause unchanged; the other uses
two real termination messages and requires PIPELINE_RUN_FAILED with the message
parameter when no cause exists. These belong to the pending Astra
[failure/event review](BATCH-EVENT-DESIGN-HANDOFF.md).

## SQL pipeline assertions

All 38 SQL registration sites have an [assertion audit](evidence/sql-complete-assertion-audit/validation.json):
29 partial ports and 9 unmapped. This is not a complete Scala-suite verdict.
The reviewed groups include:

- Basic batch cases: static dataset, escaped names, a four-view dependency chain,
  aggregation and a private-view join. Hyphen resolution matches the original
  source phase; stronger Sail publication checks remain separate from Spark V1
  catalog limitations.
- [Empty-pipeline cases](evidence/sql-empty-crosswalk/validation.json): no outputs,
  temporary-only and flow-only, with exact errors in dry/real starts.
- [Duplicate outputs](evidence/sql-duplicate-crosswalk/validation.json): cross-file
  table/view collision metadata, with a larger type/order matrix as regression
  coverage. Sink collisions remain unqualified.
- [Duplicate flows](evidence/sql-duplicate-flow-crosswalk/validation.json): same-target
  and implicit/explicit collisions, with exact identifier/destination parameters.
  Additional cases cover destination order, first-two selection, first-registered
  identifier priority and escaped names.
- [Missing producer and batch queries](evidence/sql-producer-query-crosswalk/validation.json):
  exact missing-producer metadata, scalar subquery, nested CTE and rollup results.
- [Persisted-view source text](evidence/ac7bff5007545859b6c972e2d9b9a17ffc38fa97/gate.json):
  the retained exact Rust assertion now passes unchanged. Four paired
  ordinary/pipeline publication cases cover source text, comments, Unicode and
  query results. The full original graph/type fixture and Scala suite remain
  unexecuted.
- [Catalog scope](evidence/sql-catalog-crosswalk/validation.json): four positive
  single-catalog namespace/file/private-view behaviors partially port the larger
  multi-catalog fixture. The invalid catalog-expression grid remains unmapped.

The [paired catalog probes](evidence/catalog-scope-design-boundary/provenance.json)
expose missing foldable catalog expressions, wrong missing-namespace validation
stage and differing invalid-expression error metadata. The
[shared SQL catalog handoff](SQL-CATALOG-DESIGN-HANDOFF.md) is ready for Astra;
no architecture is selected there. Full multi-catalog and streaming assertions
in the original fixture remain outstanding.

Continue reviewing assertions, expanding parameter grids and identifying helper
registrations. Full batch acceptance, original Scala-suite execution, distributed
and cancellation coverage, streaming and CDC remain incomplete.

The completed SQL audit also records partial configuration, location, partition-
rejection, ordinary-DDL rejection, declared-schema and view-comment coverage.
Three Rust registration tests now inspect the exact original partition order,
property map and per-flow configuration maps; original resolved-graph and catalog
materialization assertions remain distinct. Exact parser assertions remain gaps.
Unmapped cases include internal graph counts/input sets, catalog partition
transforms, the separate original two-database fixture, per-flow invalid-read attribution,
multipart temporary-view errors and streaming file/window refresh behavior.
The four file formats, two invalid CSV paths and six namespace pairs are explicit
source instances, not an expanded runtime denominator.

Rust test identifiers are recorded separately in each inventory case's rust_tests
field, with package, target and exact test name. Their evidence is the Rust test
log, not pytest XML. No original Scala execution is inferred from these ports.

The original non-nullable RANGE query schema now has a direct Rust PlanResolver
and declaration-validation check, separately from catalog publication. Exact
persisted-view SQL text remains a [confirmed source-preservation gap](evidence/view-source-design-boundary/provenance.json)
with a retained failing Rust test. The shared SQL design handoff now includes
source text as well as catalog expressions; TreeText reconstruction is not a
verbatim-source API. Review/status counts remain unchanged by this refinement.

The six fully/partially qualified producer/consumer pairs now have a reusable
[namespace-runner receipt](evidence/b2150a27831dbfc7b285d0d3da62305f8e302b97/gate.json).
All six pass with two Sail memory catalogs and with LakeCat as the secondary
Iceberg REST catalog, using Parquet in the primary catalog. Rows, schemas,
providers and catalog cleanup are checked. This is partial behavioral coverage
of SqlPipelineSuite:759, with no original Scala/JVM matrix run claimed.

Three batch file-format instances (Parquet/JSON/CSV) and the empty-location cause
now have partial wire ports. ORC remains a verified failure with a passing Spark
fixture/control; the [shared file-source handoff](FILE-SOURCE-DESIGN-HANDOFF.md)
records it explicitly. Original streaming output, writer setup, per-flow failure
container/attribution and missing-file instance remain unqualified.
