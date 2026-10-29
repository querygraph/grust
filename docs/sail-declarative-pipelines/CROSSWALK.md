# Spark SDP acceptance crosswalk

The pinned source inventory has 462 Scala test registration call sites, including
shared helpers and parameterized declarations. It is not an expanded runtime
test count. The Python runner's 67 executions and Sail's passing regression counts
do not qualify this whole inventory.

The first assertion-level audit covers all 11 `ViewSuite.scala` registrations at
Spark `617618396087429b5627a86ce933bb0f5d6645cb`. Seven have partial behavioral
ports in Sail; four remain unmapped. None is marked fully qualified. A further 27 materialization registrations have now been reviewed; the remaining
395 call sites still need an assertion-level audit after the additional server-suite review below. These are inventory counts,
not a completion percentage.

Each audited record in [the inventory](spark-4.2.1-inventory.json) now identifies
the phase, exact Sail test node, evidence, covered assertions, and missing
assertions. The evidence is Sail source
`e4d578ce0658f94884753e3bfdadb3f2208f5af6`, with 112 passing selected tests. The
Scala suite itself has not run against Sail. A source-level behavioral port does
not establish equivalence with Spark's internal graph objects or event assertions.

Immediate gaps exposed by the view audit:

- Missing-input errors must attribute the direct failure to the view, rather
  than merely return the underlying unresolved-table exception.
- Temporary-object rejection now checks the complete structured condition and
  parameters at Sail `5a5e256328`. Streaming-query rejection metadata remains open.
- A view whose expression lacks a permanent-view alias must fail publication;
  dependent views must receive SKIPPED events with the expected severity.
- Stored view definitions and graph metadata need exact checks alongside data
  results. A downstream aggregate alone is partial coverage of a direct view read.
- Reading a streaming table through a persisted view belongs to the later
  streaming phase. Rejecting a streaming view definition is batch validation and
  can be completed before that phase.

Continue the same assertion-level review for materialization, schema changes,
refresh selection, execution control, and event suites. Expand parameter grids
and identify helper declarations before treating registrations as executable cases.

## Materialization audit

All 27 MaterializeTablesSuite registrations are reviewed in the inventory: eight
have partial assertion ports and 19 remain unmapped. Together with ViewSuite,
38 registrations have an assertion-level review, with no full Scala-suite verdict.
Two materialization registrations expand over both full-refresh boolean values;
those instances are explicit in the records. Helpers, inheritance and other
parameter expansion remain separate work.

The suite exercises internal DatasetManager materialization. Some registerTable
fixtures contain batch queries that the Connect streaming-table API rejects.
Behavioral ports through materialized views therefore qualify shared catalog
assertions only, not the original internal entry point. The empty-materializer
case must also stay distinct from Connect's rejection of an empty pipeline.

The next independent catalog gaps are identity partition preservation and
rejection, exact post-refresh schemas, existing unknown properties, repeated
nested-container materialization, and clustering metadata. General catalog behavior belongs in Sail and must be exercised through multiple
catalog providers, including LakeCat. LakeCat changes should implement its
provider adapter, storage/CAS, authorization and persistence requirements; shared
catalog commands, schema evolution and Iceberg semantics remain in Sail. The failure/event design
checkpoint remains ready for Astra.

## Connect server audit

All 19 SparkDeclarativePipelinesServerSuite registrations are reviewed. Fourteen
have partial behavioral ports; five remain unmapped. Including the two failure-handler
registrations reviewed below, there were 59 reviewed registrations across four
suites. The eight SQL registrations below bring the total to 67, with 395 still
awaiting review. There
is no full Scala-suite verdict. The [validation record](evidence/server-crosswalk/validation.json)
binds the pinned source hash and passing Sail test nodes to the updated inventory.

The once-option grid covers both boolean values. Two output-identifier grids
have three instances each; two flow-identifier grids have two each. All ten identifier-grid instances now have exact response/identifier assertion
ports, including quoted table/flow names and the quoted custom database. Session isolation and multiple-graph execution now have protocol-level ports;
internal registry contents/counts and session-close cleanup remain gaps. Mixed SQL/protocol graph dependencies also remain open. Database-default capture
and the two exact analysis-context SQL response shapes now have explicit ports;
this does not qualify enforcement of pipeline side-effect restrictions. Two end-to-end registrations
require streaming and remain in that later phase. The missing-graph test is
named as a flow test in Spark but actually sends DefineOutput; its partial port
is mapped to the command it exercises.

## Failure-handler audit

Both PipelinesHandlerSuite registrations are reviewed and remain unmapped. One
requires rethrowing the exact existing cause; the other expands over two real
termination messages and requires PIPELINE_RUN_FAILED with the message parameter
when no cause exists. The [audit record](evidence/handler-crosswalk/validation.json)
binds the pinned source hash. These assertions join the pending Astra failure/event
design review; no error architecture is selected by this audit.

## SQL empty-pipeline assertions

Three of SqlPipelineSuite's 38 registrations are reviewed in this unit: no
outputs, temporary views only, and a standalone flow without an output. Each
has a partial Connect port that checks the exact structured error in both dry
and real runs. The [validation record](evidence/sql-empty-crosswalk/validation.json)
binds the source hash and all six passing nodes. Three API/correction controls
also match Spark 4.2.1. The internal Scala entry point remains unexecuted; the
other 35 SQL registrations still needed assertion-level review at that point.
The additional duplicate-output review below reduces that remainder to 34.

## SQL duplicate-output assertions

SqlPipelineSuite:90 now has a partial port of the cross-file table/view collision,
including the condition, SQL state and all three parameters in dry/real starts.
The [validation record](evidence/sql-duplicate-crosswalk/validation.json) binds the
pinned source and both mapped nodes. The extended 14-instance matrix also covers
reversed order, materialized/streaming table classification, persisted and
temporary views, and three duplicate definitions. Sink collisions remain
unqualified. Four of this suite's 38 registrations have now been reviewed.

## SQL missing-producer and batch-query assertions

Four further SQL registrations are reviewed: missing producer, scalar subquery,
nested CTE and group-by/rollup. Their [validation record](evidence/sql-producer-query-crosswalk/validation.json)
binds the pinned source and passing test nodes. The missing-producer error has
exact class/condition/state/identifier checks for dry/real starts; six additional
protocol cases test table/materialized/temporary outputs and escaped identifiers.
The query ports check the original result assertions through Connect. All eleven
new assertions match Spark 4.2.1. These ports bring the SQL suite to eight reviewed
registrations and leave 30 awaiting assertion audit. Original Scala-suite execution
remains unqualified. Across the inventory, 67 registrations are reviewed and 395
remain unaudited.
