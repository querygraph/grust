# Spark SDP acceptance crosswalk

The pinned inventory has 462 static Scala test registration call sites, including
helpers and parameter declarations. It is not an expanded runtime denominator.
Assertion review currently covers 71 registrations; 391 remain unaudited. None
is fully qualified by executing the original Scala suite against Sail.

| Suite | Reviewed | Partial ports | Unmapped |
| --- | ---: | ---: | ---: |
| ViewSuite | 11 | 7 | 4 |
| MaterializeTablesSuite | 27 | 8 | 19 |
| SparkDeclarativePipelinesServerSuite | 19 | 14 | 5 |
| PipelinesHandlerSuite | 2 | 0 | 2 |
| SqlPipelineSuite | 12 | 11 | 1 |
| Total | 71 | 40 | 31 |

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

Twelve of the SQL suite's 38 registration sites are reviewed; 26 await assertion
audit. The reviewed groups are:

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
