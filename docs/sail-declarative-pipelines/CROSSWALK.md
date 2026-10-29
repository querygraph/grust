# Spark SDP acceptance crosswalk

The pinned source inventory has 462 Scala test registration call sites, including
shared helpers and parameterized declarations. It is not an expanded runtime
test count. The Python runner's 67 executions and Sail's passing regression counts
do not qualify this whole inventory.

The first assertion-level audit covers all 11 `ViewSuite.scala` registrations at
Spark `617618396087429b5627a86ce933bb0f5d6645cb`. Seven have partial behavioral
ports in Sail; four remain unmapped. None is marked fully qualified. The other
451 call sites still need an assertion-level audit. These are inventory counts,
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
