# Prototype specifications

Six prototypes, each with one test file that is its whole claim; all but P3
are branches from upstream `main` on the fork (P3 builds on the integration
branch, see its note). They exist to make a decision concrete for
the maintainers, not to be merged; what survives is rewritten with their
answers. Sizes are estimates of what each adds.

Terms: see DECISION-NOTES-STREAMING.md and DECISION-NOTES-EXTENSIONS.md.
Interfaces below are sketches in Rust; names are proposals.

---

## P1. Checkpoints end to end (streaming S1, S2, S4, S9)

**Claim.** A bounded streaming query over two rate sources, unioned, filtered
and collected, checkpoints once at the end and finishes, with an in-process
coordinator assigning the id and collecting one position per source (S1:
owned by the job runner; the cluster implementation, which reaches a source
through its task, is a later prototype).

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
- `CheckpointCoordinator` in `sail-common-datafusion`, owned by the query: holds the run's sources, issues ids, waits for every source's `request_checkpoint`, stores positions in memory for the prototype, and issues the final checkpoint when every source has reported end of data. Driven by the test in the prototype; the local job runner would own it.
- The rate source implements the interface: its position is the number of rows emitted per partition; `bound_now` makes it stop after the rows already scheduled.
- The collector finishes when it has seen end of data on its input and then the next checkpoint marker, instead of when the input closes.
- Alignment happens where partitions merge (a union never interleaves partitions): the merge holds a partition after its marker until every partition's marker with the same id has arrived, then forwards one marker.

**Test.** Two rate sources at ten rows per second, bounded after one second,
unioned, filtered on an odd value, collected. Asserts: one checkpoint id
issued; two positions recorded; the collector returns exactly the rows the
sources emitted before their end positions; the union forwarded one marker per
id; the query finished without a stop request.

**Out of scope.** Durable positions, restart, watermarks, state.

**Size.** About 600 lines.

---

## P2. A table append sink with per-checkpoint commits (S6)

**Claim.** Rows received between checkpoints are committed as one
transactional append tagged with the checkpoint id, and a restart that replays
rows after the last checkpoint skips the id already committed.

**Components.**

- `CheckpointedAppendSink`, an execution plan node that consumes flow
  events, buffers data rows (retractions are an error), and on `Checkpoint {
  id }` waits for the coordinator to record the id's positions, then writes
  the buffer through the target's write path with the tag and forwards the
  marker. A restart resumes from the last id the table holds.
- Two targets: a file table (stage into `<table>/_staging/<id>`, rename into
  place at commit; an existing directory means already committed) and Delta
  through its idempotent writes (`txnAppId` = the query id, `txnVersion` =
  the checkpoint id; a write at or below the recorded version is skipped
  entirely; the last committed id is the snapshot's transaction version for
  the app id). The Delta half stands alone outside streaming and is verified
  against Spark 4.2.1 with Delta 4.4.1 (nine cases, both engines).
- A recovery test harness that runs the query, kills it after the first
  checkpoint's commit but before the coordinator records it, restarts from
  the previous positions, and checks the target.

**Test.** Two crash windows over a rate source bounded after two
checkpoints: death after checkpoint N committed resumes from N and the table
holds every row once; death after N's positions were recorded but before N
committed resumes from N minus 1, reuses id N, and again holds every row
once. The tag of the last commit equals the last checkpoint id.

**Out of scope.** Iceberg, Hive, merges, retractions.

**Size.** About 500 lines plus the harness.

---

## P3. Apache Iggy as a stream source (S10, S2)

**Claim.** A topic is read as flow events; a bounded run ends at the offsets
seen at start; a retention gap or a recreated partition fails the run.

**Components.**

- `IggyStreamSource` implementing the stream-source trait and
  `CheckpointableSource`, reusing the broker client wrapper, the message
  decoding and the schema validation already written for the bounded source.
- Markers: a checkpoint marker on request and end of data on reaching the
  start-time offsets. The watermark is not the source's: it comes from the
  watermark operator placed where the user declared it (S7).
- Positions: one offset per partition, the next offset to read (half-open,
  as the bounded source has it), paired with the partition's incarnation,
  since the broker reuses a partition's id on recreation and restarts its
  offsets at zero.
- The gap check (the first offset of every reply equals the offset asked
  for) runs on every poll, not only at resume, because the broker silently
  skips to the first retained offset. Reads never acknowledge at the broker.
- Built on the integration branch, since the client's dependency floor is
  above upstream's lockfile (S10); offered only when the floor fits.

**Test.** Against the pinned broker: produce 1,000 messages across three
partitions, run bounded, assert the collector holds all 1,000 once; produce
500 more, resume from the recorded positions, assert exactly 500 new; delete
the first retained offsets below a recorded position and assert the run
fails with the partition named.

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
  change rows with equal-sequence ties, asserting the source-position tie rule
  and that deletes keep their sequence.
- A recorded input: a file of flow events (rows with event times, interleaved
  watermark and checkpoint markers) and the expected output.

**Test.** The recorded input yields the expected windows and late count,
including both boundaries (a row at a window's end opens the next window; a
watermark equal to a window's end closes it); a null event time belongs to
no window and is dropped uncounted, as Spark's window drops it; a restart
from the second checkpoint's manifest, replaying the events after it,
reproduces the first run's remaining windows, late count and third-checkpoint
state; a snapshot under a different key type is refused; the interval
reduce resolves a tie to the later source row and lets a delete beat a
later, older-sequence upsert. Not in P4: the watermark operator itself (the
recorded input carries the markers) and the minimum across inputs at the
merge.

**Out of scope.** Sliding windows, allowed lateness, joins.

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
