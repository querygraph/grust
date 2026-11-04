# Prototype specifications

Internal specifications and evidence boundaries. P1, P2 and P4 exist as a
stack at `4fad33ca5` over upstream `62251e0a2`; P3 is `ef5f848a7` on the
integration branch. P5's separate report describes an integration-branch
fixture. P6 remains proposed. The extension specifications below are retained
as background and were not reviewed by this streaming revision.

Each experiment supports a decision, not an automatic production plan.
PROTOTYPE-RESULTS-STREAMING.md preserves historical counts and open findings.
The scopes below do not establish complete recovery, and no tests were rerun
for this document correction. Sizes are original estimates, not measurements.

Terms: see DECISION-NOTES-STREAMING.md and DECISION-NOTES-EXTENSIONS.md.
Interfaces below are sketches in Rust; names are proposals.

---

## P1. Checkpoints end to end (streaming S1, S2, S4, S9)

**Claim.** A bounded streaming query over two rate sources, unioned, filtered
and collected, checkpoints once at the end and finishes, with an in-process
coordinator assigning the id and collecting one position per source. S1
proposes job-runner ownership; the prototype is test-driven. Cluster
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
  A stream source exposes it through `fn as_checkpointable(&self) -> Option<&dyn CheckpointableSource> { None }` on the stream-source trait, the only change to that trait.
- `CheckpointCoordinator` in `sail-common-datafusion`, owned by the query: holds the run's sources, issues ids, waits for every source's `request_checkpoint`, stores positions in memory for the prototype, and issues the final checkpoint when every source has reported end of data. Driven by the test in the prototype; job-runner ownership is proposed only if the selected recovery domain fits one job.
- The rate source implements the interface: its position is the number of rows emitted per partition; `bound_now` makes it stop after the rows already scheduled.
- The collector finishes when it has seen end of data on its input and then the next checkpoint marker, instead of when the input closes.
- Alignment happens where partitions merge (a union never interleaves partitions): the merge holds a partition after its marker until every partition's marker with the same id has arrived, then forwards one marker. The same merge combines watermarks as the minimum over running inputs (S7), tested with a fixed interleaving of three inputs where an ended input and a closed input each raise the minimum.

**Test.** Two rate sources at ten rows per second, bounded after one second,
unioned, filtered on an odd value, collected. Asserts: one checkpoint id
issued; two positions recorded; the collector returns exactly the rows the
sources emitted before their end positions; the union forwarded one marker per
id; the query finished without a stop request.

**Out of scope.** Durable positions, restart, watermark generation, state,
and cluster coordination. Recorded watermark combination is included.

**Review gap.** Test staggered end-of-data and closure separately, and
concurrent checkpoint requests. The current merge can count an ended input
again when it closes; a latest-value request channel can skip an identifier.
These source-review findings are not reproduced execution results.

**Size.** About 600 lines.

---

## P2. A table append sink with per-checkpoint commits (S6)

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
  the app id). The Delta half stands alone outside streaming; its historical report lists
  nine cases on each engine, Spark 4.2.1 with Delta 4.4.1 and Sail.
- A recovery harness with a replayable integer-row test source, distinct
  from the rate source. It records positions before permitting a file-table
  commit, then interrupts either before or after that commit.

**Test.** Two simulated crash windows over the replayable fixture: interruption
after checkpoint N commits resumes from N; interruption after N's positions are recorded
but before its commit resumes from N minus 1 and reuses N at another boundary.
Both checks expect every row once in the sole target. That identifier reuse
is not safe when another sink already committed N.

**Review gap.** S6 must choose the recovery domain. A small transition model
can illustrate partial-commit loss, duplication and fixed-boundary replay;
it cannot substitute for a future two-effect execution test. The Delta
concurrent-creation inference also needs a separate reproduction before a PR.

**Out of scope.** Multiple sinks, integrated Delta streaming recovery,
Iceberg, Hive, merges, retractions and durable coordinator storage.

**Size.** About 500 lines plus the harness.

---

## P3. Apache Iggy as a stream source (S10, S2)

**Intended claim.** A topic is read as flow events, a bounded run stops at
captured source offsets, and retention gaps or changed incarnations fail.
The existing tests cover specific resume cases, not every bounding race.

**Components.**

- `IggyStreamSource` implementing the stream-source trait and
  `CheckpointableSource`, reusing the broker client wrapper, the message
  decoding and the schema validation already written for the bounded source.
- Markers: a checkpoint marker on request and end of data on reaching the
  start-time offsets. P3 emits no watermark. An event-time operator and its
  marker obligations remain S7's proposed choice.
- Positions: one offset per partition, the next offset to read (half-open,
  as the bounded source has it), paired with the partition's incarnation,
  since the broker reuses a partition's id on recreation and restarts its
  offsets at zero.
- The gap check (the first offset of every reply equals the offset asked
  for) runs on every poll, not only at resume, because the broker silently
  skips to the first retained offset. Reads never acknowledge at the broker.
- Built on the integration branch, since the client's dependency floor is
  above upstream's lockfile (S10); offered only when the floor fits.

**Test.** Against the pinned broker, through the scan, the merge and the
collector with the coordinator bounding and finishing the run: 1,000
messages across three partitions are read once each and the recorded
position is 333, 333 and 334; after 500 more, a resume reads exactly ids
1,000 to 1,499; a resume from an offset that retention has removed fails
naming the partition and the expected offset; a resume onto a deleted,
recreated and refilled partition fails naming the partition and its
incarnation. Every poll goes through the bounded reader's exact-range read,
so the gap and incarnation checks run on every page. Not in P3: registering
the source for the pipelines' `readStream.format("iggy")` path, which still
builds the bounded source.

**Review gap.** Recreate a partition after scan but before bounding, with
an empty replacement. Check that incarnation validation happens before an
end marker. Also test capture of one partition's bound while another metadata
request is delayed and readers continue consuming. Existing tests do not
establish either interleaving.

**Size.** About 800 lines, most of it moved.

---

## P4. A windowed aggregate with state (S5, S7, S8)

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

**Test.** The recorded input yields the expected windows and late count,
including both boundaries (a row at a window's end opens the next window; a
watermark equal to a window's end closes it); a restart
from the second checkpoint's manifest, replaying the events after it,
reproduces the first run's remaining windows, late count and third-checkpoint
state; a snapshot under a different key type is refused; the interval
reduce resolves a tie to the later recorded row and lets a delete beat a
later, older-sequence upsert. Not in P4: the watermark operator itself (the
recorded input carries the markers) and the minimum across inputs at the
merge.

**Out of scope.** Sliding windows, joins, a live watermark generator,
replay under another source interleaving, safe cleanup and power-loss
publication guarantees.

**Review gap.** The implementation skips null event times without counting
them, but the recorded fixture does not test that case. S5 must retain state
needed by incomplete sink effects.
S7 must settle the existing marker contract before implementing late-data
semantics. The recorded input does not prove equivalence to Spark's batch
watermark behavior. Snapshot cost and memory under stalled watermarks remain
unmeasured.

**Size.** About 900 lines.

---

## P5. Loading Comet's scalar UDF library (extensions E1)

**Claim.** A library built with Comet's UDF SDK loads into Sail through its
discovery symbol and version probe, and its functions run from Spark SQL.

**Components.**

- A loader in `sail-session`'s extension module: open the library, call the
  version probe and refuse a mismatch, call the discovery symbol, wrap each
  kernel as a DataFusion scalar UDF that calls `init` for the return type and
  `execute` per batch, converting arrays through the Arrow C Data Interface;
  the library handle is kept alive for the process.
- A Sail-owned fixture library, `sail-c-udf-fixture`, that fills the C
  structs by hand with two kernels, `add_one_c` and `sub_c` (argument order
  observable), so the boundary is exercised without building any external
  code. Comet's own test library and Sedona's functions are the second step,
  run by the owner, since building downloaded code is outside this session's
  permissions.
- Built on the integration branch, where the extension loader that will own
  the second channel lives; the crate itself (`sail-c-udf`: the C layout, the
  loader with the version probe, the kernel-as-scalar-function adapter) has
  no dependency on anything the branch added and applies to upstream `main`
  as is.

**Test.** Through DataFusion's frame API over a three-row batch: `add_one_c`
gives 2, 6 and null; `sub_c(a, b)` and `sub_c(b, a)` give opposite signs; a
kernel error (`sub_c` with one argument) names the function and the reason; a
library without the version probe is refused by name. The panic-containment
and Spark SQL cases follow once the loader hook is in.

**Size.** About 400 lines plus the fixture build.

---

## P6. A Sedona C table provider through the relation dispatch (E2)

**Claim.** A table provider defined by Sedona's header is imported as a
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

**Size.** About 500 lines, excluding the adapters if they come from Sedona's
crate.
