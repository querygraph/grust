# Spark SDP acceptance crosswalk

The pinned source inventory has 462 Scala test registration call sites, including
shared helpers and parameterized declarations. It is not an expanded runtime
test count. The Python runner's 67 executions and Sail's passing regression counts
do not qualify this whole inventory.

The first assertion-level audit covers all 11 `ViewSuite.scala` registrations at
Spark `617618396087429b5627a86ce933bb0f5d6645cb`. Seven have partial behavioral
ports in Sail; four remain unmapped. None is marked fully qualified. A further 27 materialization registrations have now been reviewed; the remaining
424 call sites still need an assertion-level audit. These are inventory counts,
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
