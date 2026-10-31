# Internal table metadata materialization

This checkpoint implements Spark's metadata seam independently of flow execution.
It follows the user-notified CF-0438 checkpoint and CF-0440/0441 boundary correction.
It does not activate streaming, Iggy, CDC, or the public incremental execution path.

## Source contract and executable reference

Spark source pin: `617618396087429b5627a86ce933bb0f5d6645cb` (4.2.1).
`MaterializeTablesSuite.scala:125–161` registers two **streaming tables**, using
batch DataFrame functions, then checks nullable INT `x` and STRING `y` columns.
`:374–399` registers a streaming table with declared nullable INT `x1,x2` and
ordered identity partition `x2`. Neither assertion executes flows.
`TestGraphRegistrationContext.scala:45–72` sets `isStreamingTable=true`;
substituting a materialized view would change the tested contract.
`BaseCoreExecutionTest.scala:29–40` calls `DatasetManager.materializeDatasets`.

A standalone Scala adapter compiles the unmodified original registration helper
against the installed 4.2.1 production jars and invokes that DatasetManager.
It reproduces both original assertions and additionally checks table kinds and
zero rows. This is a two-assertion internal reference, not execution of the
original ScalaTest suite. Initial adapter compilation failed on an unnecessary
companion import; that attempt is retained separately.

## Sail seam and ownership

`pipelines/materialize.rs::tables` already prepares and consumes Sail command
plans through the session JobService. The execution runner owns physical command
streams; consumption is required for catalog effects. The analyzed graph retains
schemas and definitions, not provider leases. The table helper accepts only the resolved schema map it actually needs;
full execution analysis still validates batch/streaming flow kinds. The native
adapter resolves the independent fixture queries and uses schema::infer without
relabeling outputs or entering public execution. No new catalog API, executor,
public protocol, or Grust dependency is necessary for this change.

`execution::execute` continues rejecting any Table/Sink graph **before** calling
this materializer. A native test can invoke the private metadata helper with an
resolved Table schemas; this does not authorize a public execution bypass. Tests
also call the public execution implementation on a mixed MV/Table graph and
assert neither catalog target is created. The guard fixture supplies resolved
metadata directly; the selected public regressions cover the actual execution
entry point. It does not assert that full analysis accepts batch Table flows.

## First implementation chunk

- Include Table and MaterializedView outputs in the private table materializer;
  continue excluding temporary/persisted views, sinks, and unselected outputs.
- Creation uses the existing provider validation and CreateTable command path.
  Inferred schemas become recursively nullable; declared schemas remain exact.
  Properties, comments and ordered identity partitioning reuse the same path.
- For an existing Table on ordinary refresh, do not truncate. Convert existing
  catalog fields through the existing Spark schema bridge, merge existing schema
  on the left using `schema_merge::merge_fields`, and apply the existing column
  diff/property path. Existing field order and metadata win; nullability widens,
  new fields append, incompatible types fail before mutations for that target.
- Materialized views retain their existing replacement/truncate behavior.
- Streaming full reset is explicitly unavailable in this chunk. Preflight the
  entire graph before any catalog mutation, including absent targets. Canonical
  `pipelines.reset.allowed=false` downgrades full reset to ordinary refresh, as
  Spark does. An allowed full reset returns unsupported before any target effect.

The full-reset guard is a temporary implementation boundary, not final parity.
Its whole-graph preflight is a Sail unsupported-mode policy: Spark materializes
table by table, so a later supported-table failure can leave earlier targets.
We do not claim identical partial-state timing for this unimplemented reset.
Spark's full refresh truncates existing data and unconditionally drops the
reserved AutoCDC auxiliary table even when the target is absent. Adding that
name-derived deletion without the standing owned CDC effect contract would be
premature. This chunk neither silently omits that deletion nor claims reset parity.

## Qualification and next chunks

Native tests must prove the two original metadata assertions, no rows written,
ordinary refresh preserving existing rows/columns/comments while adding columns
and properties, incompatible-merge retention, partition-change rejection,
reset.allowed=false retaining rows/fields, reset preflight, and unchanged
public execution rejection. Exact detached fmt/strict Clippy/library gates cover
the implementation; selected public regressions guard existing batch behavior.
Production-only parent controls must fail on the new native metadata assertions.

Still required for this seam: mutation-failure attribution and origin parity,
normalized storage-path propagation, backend-specific alter behavior, full reset
and owned auxiliary cleanup, and broader original materialization assertions.
General Sail catalog gaps belong in Sail; LakeCat remains one supported adapter.
No inventory site becomes a full Scala execution on the strength of this adapter.

The next substantial design checkpoint is the full-reset/owned CDC cleanup path;
notify the user before starting it so they can choose Astra. Ordinary internal
metadata implementation and qualification continue under this checkpoint.

Review: Fable CF-0443 / Grust `667a4720` confirms source claims and this staged
boundary, with per-table failure attribution still open. Spark ordinary refresh
reference also passes existing-left comments/order, property update and retained
rows. Spark uses its default session catalog; Sail native tests use memory
catalog plus real Parquet data. LakeCat alter parity is not inferred from either.
