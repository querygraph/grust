# Spark SDP acceptance crosswalk

The legacy owned-root inventory has462 static Scala test registration call sites, including
helpers and parameter declarations. It is not an expanded runtime denominator.
Assertion review currently covers 97 registrations; 365 remain unaudited. None
is a full Sail conformance verdict; the [execution design](ORIGINAL-SUITE-EXECUTION-DESIGN.md)
requires route-specific evidence preserving all original assertions.

| Suite | Reviewed | Partial ports | Unmapped |
| --- | ---: | ---: | ---: |
| ViewSuite | 11 | 7 | 4 |
| MaterializeTablesSuite | 27 | 15 | 12 |
| SparkDeclarativePipelinesServerSuite | 19 | 14 | 5 |
| PipelinesHandlerSuite | 2 | 0 | 2 |
| SqlPipelineSuite | 38 | 32 | 6 |
| Total | 97 | 68 | 29 |

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
32 partial ports and 6 unmapped. This is not a complete Scala-suite verdict.
The reviewed groups include:

- [Temporary-view qualifiers](evidence/temporary-view-qualifiers/README.md):
  SqlPipelineSuite:599's arbitrary database qualifier produces ParseException/
  INVALID_TEMP_OBJ_QUALIFIER on both engines. Native analyzer/planner/Connect
  metadata and pipeline draft rollback are checked, with valid SESSION forms
  separately exercising private/direct view execution.

- [Multipart outputs](evidence/original-multipart/README.md): SqlPipelineSuite:562's
  two namespace-qualified materialized views register together; both return Row(1)
  on Spark 4.2.1 and Sail. Owned graph/table/database cleanup passes. The current
  memory/memory catalog runner also rechecks the five already-covered :634 answers.

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
  multi-catalog fixture. Both invalid catalog-expression grid values now have partial behavioral ports
  with native registration error metadata in
  [992f5bcbf](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/gate.json); the original Scala suite is unexecuted.

The [paired catalog probes](evidence/catalog-scope-design-boundary/provenance.json)
record the historical expression/namespace/error failures. Shared expression
activation now passes all thirteen retained registration assertions, after the
[shared ANSI work](evidence/87a7c941d30c952e6c928e1a6d2b4aec2b45abf6/gate.json). Twenty-seven
new public instances pass unchanged on Spark 4.2.1 and Sail. Five broader cast-family
failures remain recorded; full multi-catalog and streaming assertions in the
original fixture remain outstanding.

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
persisted-view SQL text has a [retained historical failure](evidence/view-source-design-boundary/provenance.json)
and now passes its unchanged Rust assertion plus four paired publication controls. The shared SQL design handoff now includes
source text as well as catalog expressions; TreeText reconstruction is not a
verbatim-source API. Review/status counts remain unchanged by this refinement.

The six fully/partially qualified producer/consumer pairs now have a reusable
[namespace-runner receipt](evidence/b2150a27831dbfc7b285d0d3da62305f8e302b97/gate.json).
All six pass with two Sail memory catalogs and with LakeCat as the secondary
Iceberg REST catalog, using Parquet in the primary catalog. Rows, schemas,
providers and catalog cleanup are checked. This is partial behavioral coverage
of SqlPipelineSuite:759, with no original Scala/JVM matrix run claimed.

All four batch file-format instances (Parquet/ORC/JSON/CSV) now have partial
direct-MV wire ports, with the [ORC public receipt](evidence/orc-public-registration/README.md)
qualifying the retained ORC instance at Sail `07fa5d5bee`. A separate probe uses
the retained Spark-written RANGE file for the original no-USING CTAS call and
direct batch MV, checking rows 0,1,2, nullable BIGINT schema and the CTAS's default
Parquet provider. The added CTAS command-result `.collect()` failed on UInt64
conversion; that failure remains separate from the passing original call shape.
The [shared file-source handoff](FILE-SOURCE-DESIGN-HANDOFF.md) and earlier failure
receipts remain historical evidence. Original Sail ORC writer setup and streaming
output b remain unqualified, as do per-flow failure container/attribution and the
missing-file instance. The empty-location cause retains its partial wire port.
This extends one already mapped parameter grid: 462 static registrations, 97
reviewed and 59 partial ports remain unchanged; no original Scala suite is qualified.


SqlPipelineSuite:634's combined two-file fixture now has all five original output
assertions retained in `catalog_scope.py`, including `STREAM` of a batch CTE.
Both memory/memory and memory/LakeCat profiles pass with schema/provider checks
and metadata cleanup; see the [receipt](evidence/8d044db3860b4f55e49543c833246af31e986e2e/gate.json).
The inventory remains 462 static registrations, 97 audited and 59 partial ports:
this strengthens an already mapped case and does not establish original Scala
execution. Four paired Spark 4.2.1 CTE cases support the shared classifier fix;
277 selected Python and 67 upstream executions pass on the new CLI.

## Repeated nested materialization schema ports

Recorded 2026-10-30T02:41:33.921674+00:00. [Sail `f6f1328192`](evidence/nested-materialization/README.md) passes two partial ports of MaterializeTablesSuite735/780, preserving six exact nested schemas after two catalog-output refreshes. The original internal fixture remains distinct from fresh public Connect graphs; the failed same-graph attempt is retained. The existing462 registrations now include61 partial ports; no original Scala-suite execution is claimed.

## Internal metadata table ports

[Exact Sail a9eecf5f5 evidence](evidence/internal-table-metadata/README.md) adds
partial ports for MaterializeTablesSuite:125 and :374 through the private
metadata seam, preserving streaming Table kinds and batch function schemas.
Spark production DatasetManager passes the same catalog assertions using the
original registration helper; no original ScalaTest suite was executed against
Sail. Native189, production-only control1pass/3fail, fresh public300+67 pass.
At that increment:65 partial/397 unmapped,97 reviewed/462 static sites.
Streaming execution, full-reset owned cleanup and remaining metadata contract
coverage are still open; see the [design](METADATA-TABLE-MATERIALIZATION-DESIGN.md).

## Metadata partition diagnostics

[Sail604a91f8d evidence](evidence/materialization-partition-errors/README.md)
adds partial ports of MaterializeTablesSuite:467/:1050 and the rejection portion
of :402. Native structured diagnostics and Connect ErrorInfo retain class,
condition, SQL state and parameters; catalog transform/target-state assertions
pass. :402 success/schema assertions, JVM outer materialization wrapper and
origins remain open. Exact native191, unchanged control0/2, Spark3 cases and fresh
public300+67 pass; original ScalaTest execution against Sail is still false.
Current canonical total:68 partial/394 unmapped,97 reviewed/462 static sites.

## Exact basic metadata and matching existing schema

[Test-only Sail807d66b15 evidence](evidence/basic-metadata-refresh/README.md)
strengthens already partial :42/:236 with exact native integer/comment fixtures
and two verbatim original Spark test-body references. Native193 and comment-removal
control0/1 pass. Production paths match publicly qualified parent604; no new public
run/build is claimed. Totals remain68 partial/394 unmapped,97 reviewed/462 static.
The original suite has not executed against Sail. Original-suite execution harness
is the next user-notified Astra design checkpoint.

## Original-suite reference and scope checkpoint

[Exact Grust70a634e2 evidence](evidence/original-suite-substrate/README.md)
registers554 owned-root runtime names and passes original Default/Hive metadata
suites29 each on Spark. These are reference outcomes, not Sail acceptance, and
no native site is promoted. [20 outside-root declarations](spark-4.2.1-scope-expansion.json)
remain to reconcile, including parser inheritance/direct SQL rejection/session
cache lifecycle. Neither legacy462 nor owned554 is the complete goal denominator.
Next: extend collection/inventory, map full fixtures/assertions and implement the
[declared Sail routes](ORIGINAL-SUITE-EXECUTION-DESIGN.md).
