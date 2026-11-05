# Experiments for streaming recovery and extension interfaces

These experiments isolate mechanisms needed for streaming recovery and
extension interfaces in Sail. Each specifies a claim, components, test and
coverage limits. Passing a component test does not establish an integrated
source-to-table recovery protocol.

A flow event is a data batch or an ordered control marker. A checkpoint
identifies a boundary through source positions and operator state. End of
data marks a source's bounded end, while a watermark constrains which older
timestamps may follow. A retraction cancels an earlier row. The experiment
labels below identify independent mechanisms; they are not an implementation
schedule. Rust interfaces are proposed sketches.

---

## P1. Checkpoint transport and bounded completion

**Claim.** A bounded streaming query over two rate sources, unioned, filtered
and collected, checkpoints once at the end and finishes, with an in-process
coordinator assigning the id and collecting one position per source. The
prototype is driven by its test harness. Job-runner ownership is a production
option when the recovery domain, the writes tracked together, fits one job. Cluster
coordination remains outside this experiment and depends on the selected
scope.

**Components.**

- `CheckpointableSource`, a new interface in `sail-common-datafusion`:
  ```rust
  pub trait CheckpointableSource: Send + Sync {
      /// Ask the running scan to emit `Checkpoint { id }` after the rows it has
      /// produced so far; returns once the marker has been emitted on every
      /// partition.
      fn request_checkpoint(&self, id: u64) -> BoxFuture<'_, Result<()>>;
      /// The position the source reached at `id`, opaque to the coordinator.
      fn position(&self, id: u64) -> BoxFuture<'_, Result<Vec<u8>>>;
      /// Fix the end position now (bounded run); the scan emits `EndOfData`
      /// on reaching it.
      fn bound_now(&self) -> BoxFuture<'_, Result<()>>;
  }
  ```
  The stream-source trait exposes this optional capability through
  `as_checkpointable`, returning `None` by default.
- `CheckpointCoordinator` holds the sources, assigns identifiers, waits for
  requested markers and records positions in memory. The test drives a final
  checkpoint after all sources report end of data.
- The rate source implements the interface: its position is the number of rows emitted per partition; `bound_now` makes it stop after the rows already scheduled.
- The collector finishes when it has seen end of data on its input and then the next checkpoint marker, instead of when the input closes.
- A merge holds each partition at its checkpoint marker until all partitions
  reach that identifier, then forwards one marker. A recorded three-input
  schedule tests the minimum watermark and its changes when inputs end.

**Test.** Two rate sources at ten rows per second, bounded after one second,
unioned, filtered on an odd value, collected. Asserts: one checkpoint id
issued; two positions recorded; the collector returns exactly the rows the
sources emitted before their end positions; the union forwarded one marker per
id; the query finished without a stop request.

**Out of scope.** Durable positions, restart, watermark generation, state,
and cluster coordination. Recorded watermark combination is included.

**Uncovered cases.** Test staggered end-of-data and closure separately, and
concurrent checkpoint requests. The current merge can count an ended input
again when it closes; a latest-value request channel can skip an identifier.
These are source-inspection findings, not reproduced execution results.

---

## P2. A table append sink with checkpoint commits

**Claim under test.** One file-table sink can recover both sides of its
commit boundary with a replayable test source. Separate Delta tests exercise
idempotent-write options. There is no integrated Delta streaming-restart
claim.

**Components.**

- `CheckpointedAppendSink`, an execution plan node that consumes flow
  events, buffers data rows (retractions are an error), and on `Checkpoint {
  id }` waits for the coordinator to record the id's positions, then writes
  the buffer through the target's write path with the tag and forwards the
  marker. A restart resumes from the last id the table holds.
- A file target plus a separate Delta write-option experiment: the file table
  stages into `<table>/_staging/<id>`, then renames into
  place at commit; an existing directory means already committed. Delta is
  exercised separately through its idempotent writes (`txnAppId` = the query id, `txnVersion` =
  the checkpoint id; a write at or below the recorded version is skipped
  entirely; the last committed id is the snapshot's transaction version for
  the app id). The Delta half stands alone outside streaming; reported runs cover
  nine cases on each engine, Spark 4.2.1 with Delta 4.4.1 and Sail.
- A recovery harness with a replayable integer-row test source, distinct
  from the rate source. It records positions before permitting a file-table
  commit, then interrupts either before or after that commit.

**Test.** Two simulated crash windows over the replayable fixture: interruption
after checkpoint N commits resumes from N; interruption after N's positions are recorded
but before its commit resumes from N minus 1 and reuses N at another boundary.
Both checks expect every row once in the sole target. That identifier reuse
is not safe when another sink already committed N.

**Uncovered cases.** The test covers one table transaction. A small transition model
can illustrate partial-commit loss, duplication and fixed-boundary replay;
it cannot substitute for a two-effect execution test. The possible duplicate
write during concurrent Delta table creation also needs a controlled reproduction.

**Out of scope.** Multiple sinks, integrated Delta streaming recovery,
Iceberg, Hive, merges, retractions and durable coordinator storage.

---

## P3. Apache Iggy as a stream source

Apache Iggy is a message broker that stores data in partitions. A partition
incarnation distinguishes a recreated partition from the original.

**Intended claim.** A topic is read as flow events, a bounded run stops at
captured source offsets, and retention gaps or changed incarnations fail.
The existing tests cover specific resume cases, not every bounding race.

**Components.**

- `IggyStreamSource` implementing the stream-source trait and
  `CheckpointableSource`, reusing the broker client wrapper, the message
  decoding and the schema validation already written for the bounded source.
- Markers: a checkpoint marker on request and end of data on reaching the
  start-time offsets. P3 emits no watermark. An event-time operator and its
  marker obligations need a separate contract.
- Positions: one offset per partition, the next offset to read (half-open,
  as the bounded source has it), paired with the partition's incarnation,
  since the broker reuses a partition's id on recreation and restarts its
  offsets at zero.
- The gap check (the first offset of every reply equals the offset asked
  for) runs on every poll, not only at resume, because the broker silently
  skips to the first retained offset. Reads never acknowledge at the broker.
- The client requires dependencies newer than the inspected Sail baseline.
  Its admission depends on resolving those dependency requirements.

**Test.** Read 1,000 messages across three partitions exactly once, with
positions 333, 333 and 334. After appending 500 messages, resume and read ids
1,000 to 1,499. Reject an offset below retention with the partition and expected
offset named. Reject a recreated partition with its incarnation named. Every
poll uses the exact-range reader. Planner registration for
`readStream.format("iggy")` is outside this experiment.

**Uncovered cases.** Recreate a partition after scan but before bounding, with
an empty replacement. Check that incarnation validation happens before an
end marker. Also test capture of one partition's bound while another metadata
request is delayed and readers continue consuming. Existing tests do not
establish either interleaving.

---

## P4. A windowed aggregate with state

A tumbling window groups timestamps into fixed, non-overlapping intervals.
A manifest lists the files that make up one saved state snapshot.

**Claim.** An event-time tumbling window aggregate emits a window's result
when the watermark passes its end, drops and counts late rows, snapshots its
state to a segment at each checkpoint, and recovers from the manifest.

**Components.**

- `WindowedAggregateExec` consuming flow events: rows go to per-window,
  per-key partial state; a row is dropped and counted only when every window
  it belongs to has ended at or before the watermark; a watermark marker
  closes windows whose end is at or below it and emits their results as data
  rows; a checkpoint marker writes the open state as one Arrow file segment
  and a manifest for that checkpoint.
- The state store: `<checkpoint location>/<run>/state/<operator>/<id>.arrow`
  plus `manifest-<id>.json` naming the live segments at that checkpoint;
  recovery loads the manifest of the recorded checkpoint, and a snapshot is
  refused under column types other than those it was written with.
- A companion test for change capture: an interval-reduce over recorded
  change rows with equal-sequence ties, asserting the recorded row-order rule
  and that deletes keep their sequence. This is a whole-batch function, not
  a demonstrated streaming interval accumulator.
- A recorded input: a file of flow events (rows with event times, interleaved
  watermark and checkpoint markers) and the expected output.

**Test.** Verify window results and late count, including timestamps at the
window boundary. A row at the end opens the next window; a watermark equal
to the end closes it. Restore the second snapshot and reproduce remaining
results and third-checkpoint state. Reject a changed key type. Reduction
selects the later recorded row for a tie and preserves a delete over a later,
older-sequence upsert. Watermark generation and multi-input combination are
outside this experiment.

**Out of scope.** Sliding windows, joins, a live watermark generator,
replay under another source interleaving, safe cleanup and power-loss
publication guarantees.

**Uncovered cases.** The implementation skips null event times without counting
them, but the recorded fixture does not test that case. State needed by
incomplete sink effects must remain available. Sail’s watermark marker
promises that older timestamps will not follow; late-data handling must
enforce or explicitly revise that contract. The recorded input does not prove equivalence to Spark's batch
watermark behavior. Snapshot cost and memory under stalled watermarks remain
unmeasured.

---

## P5. Loading scalar functions through the Arrow C interface

**Intended claim.** A library built with Apache DataFusion Comet’s scalar
function SDK loads into Sail through its discovery symbol and version probe,
and its functions run from Spark SQL. The implemented fixture tests the C
layout directly; it does not establish compatibility with external libraries.

**Components.**

- A loader in `sail-session`'s extension module: open the library, call the
  version probe and refuse a mismatch, call the discovery symbol, wrap each
  kernel as a DataFusion scalar UDF that calls `init` for the return type and
  `execute` per batch, converting arrays through the Arrow C Data Interface;
  the library handle is kept alive for the process.
- A Sail-owned fixture library, `sail-c-udf-fixture`, that fills the C
  structs by hand with two kernels, `add_one_c` and `sub_c` (argument order
  observable), so the boundary is exercised without building any external
  code. Compatibility also needs execution against Comet's own library and
  Apache Sedona's spatial functions. Those external binaries remain untested.
- The `sail-c-udf` crate holds the C layout, version-probing loader and
  scalar-function adapter. Its dependencies are Arrow, DataFusion's expression
  crate and the loading library; the separate package-loader hook remains
  an integration requirement.

**Test.** Through DataFusion's frame API over a three-row batch: `add_one_c`
gives 2, 6 and null; `sub_c(a, b)` and `sub_c(b, a)` give opposite signs; a
kernel error (`sub_c` with one argument) names the function and the reason; a
library without the version probe is refused by name. The panic-containment
and Spark SQL cases follow once the loader hook is in.

---

## P6. A Sedona C table provider through relation dispatch

**Proposed experiment.** A table provider defined by Apache Sedona's header is imported as a
DataFusion table provider and scanned through Sail's bounded-relation
dispatch, with a child plan exported across the same boundary.

**Components.**

- Import adapter for `SedonaCTableProvider` and `SedonaCExecutionPlan`
  (from Sedona's crate if the dependency is accepted, else carried with
  attribution); export adapter for a DataFusion execution plan to
  `SedonaCExecutionPlan`.
- The bounded-relation dispatch replaced for one relation type: the child
  plans are exported, the extension returns a C execution plan, it is
  imported and executed.

**Test.** A test provider built against the header that returns its input's
rows doubled; a Spark Connect relation extension carrying it over a
`VALUES` child returns the doubled rows; the imported plan's schema and
properties round-trip.
