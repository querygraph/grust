# Evidence for streaming recovery mechanisms

Four component experiments exercise Sail's flow events, which carry data
batches and ordered control markers. The tables below summarize reported
runs on the code versions listed at the end. Source-inspection findings
are identified separately from executed tests. None of these results establishes a complete durable source-to-table recovery
protocol or the proposed deterministic change-event semantics. Reported counts
below belong to the experimental implementations; they were not rerun as an
integrated qualification.

A checkpoint identifies an input boundary and associated state. A bounded
source emits end of data when it reaches its captured end position. A
watermark constrains which older timestamps can follow. An output effect
is one table write that can complete separately from another.

## P1 Checkpoint markers and alignment

**Question.** Can a coordinator request checkpoint markers, collect source
positions and finish a bounded query through the existing event model?

**Reported result.** The test-driven, in-process coordinator records
positions in memory. A merge aligns equal checkpoint identifiers across
inputs. Controlled runs combine watermarks and finish after end of data and
a checkpoint. The rate source's position is a row counter for exercising the
protocol; it does not make time-dependent rate rows replayable.

| Reported test | Reported passes |
| --- | --- |
| Two rate sources unioned, filtered, merged and collected | 20 of 20 |
| Marker order from four partitions | 20 of 20 |
| Watermark combination over three inputs | 20 of 20 |

**Decision evidence.** A coordinator can exercise these mechanisms in local
mode without introducing a driver. Whether it belongs to a job runner depends on which writes must recover together.

**Limits.** No durable coordinator, cluster transport or recovery test.
Source review found that end and close can count the same input twice, and
that overlapping checkpoint requests can strand different inputs at
different barriers. The reported schedules do not exercise these cases.
These failure schedules have not been reproduced in the reported runs.

## P2 Tagged append and separate Delta writes

**Question.** Can an append sink recover both sides of a commit crash window?

**Reported result.** A replayable test source feeds one file-table sink.
Positions are recorded before the sink commits. The harness simulates a
crash by aborting the reader task and retaining positions in memory. An
interruption after commit resumes from that checkpoint; one before commit
replays from the previous one.
The harness can reuse an uncommitted identifier at a new boundary only
because its sole sink has not committed it.

A separate Delta prototype implements the application identifier and
transaction version options for idempotent writes. Its tests exercise those
options directly; they are not an integrated Delta streaming-restart test.

| Reported test | Reported passes |
| --- | --- |
| File sink simulated crash after commit | 20 of 20 |
| File sink simulated crash before commit | 20 of 20 |
| Delta idempotent-write cases on Sail | 9 of 9 |
| Same cases on Spark 4.2.1 with Delta 4.4.1 | 9 of 9 |

**Decision evidence.** Recording positions before a commit is necessary.
It is not sufficient for several sinks or the two change-capture effects.
Reusing an identifier at a different boundary can skip rows in an already
committed sink. The recovery scope must distinguish one table transaction
from a flow with several table effects.

**Limits.** No integrated Delta checkpoint sink, multiple-sink crash test,
change-capture merge, retractions or other table formats. A source-path
inference identifies a possible duplicate write when two plans see an absent
Delta table and use the same transaction identity. That inference needs a
controlled reproduction before the write path can be treated as safe.

## P3 Iggy positions and exact-range reads

Apache Iggy is a partitioned message broker. A partition incarnation
distinguishes a recreated partition from the original.

**Question.** Can an Iggy source resume while detecting retained-data gaps
and partition recreation?

**Reported result.** Reads use the bounded adapter's exact-range reader.
Positions contain the next offset and partition incarnation. The reported
cases detect a resume below retention and recreation before scanning.

| Reported broker test | Reported result |
| --- | --- |
| Bounded run reads each message once | Pass |
| Resume reads each new message once | Pass |
| Resume below retained data fails | Pass |
| Resume onto a recreated partition fails | Pass |
| These cases repeated on idle cores | 20 of 20 |
| These cases repeated with all cores saturated | 15 of 15 |

Reported execution also caught retention overtaking a resume during a run
through the exact-range check. Stream termination can precede coordinator
completion, so the caller must account for both events.

**Decision evidence.** Source completion and durable run completion need
separate accounting. Incarnation belongs in every recoverable position.

**Limits.** Source review found a gap when a partition is recreated between
scan and bounding: end-of-data can precede the incarnation check. Bound
capture racing ongoing consumption also needs a controlled test. These cases
are outside the reported test coverage. Planner registration and dependency alignment remain
outside the prototype. Saved positions also need binding to the complete source
descriptor and a partition-set/discovery policy. Payload-only decoded rows do
not automatically preserve the incarnation-bearing provenance required by
change-event normalization.

## P4 Recorded window state and interval reduction

**Question.** Can a window operator snapshot and restore state for a recorded
event sequence?

**Reported result.** A tumbling window groups timestamps into fixed, non-overlapping intervals
and counts and sums per key. Recorded
watermark markers close windows and determine the late-row count. Each
checkpoint writes the full open state as an Arrow segment and then its
manifest, which names the snapshot files, using rename. Recovery reads the requested checkpoint and refuses
incompatible column types. A separate function reduces an already collected
batch of change rows, resolving ties by its row order and retaining deletes
with sequence values.

| Reported test | Reported passes |
| --- | --- |
| Windows and late count on recorded input | 20 of 20 |
| Restart reproduces remaining output and final state | 20 of 20 |
| Snapshot under another key type is refused | 20 of 20 |
| Interval reduction with a tie and a delete | 20 of 20 |

The reported negative control disables restore and fails the restart and
schema-refusal tests.

**Decision evidence.** File snapshots support recovery for that fixed merged
event order. They do not prove recovery under another source interleaving.
The tie test proves recorded row order. Its arbitrary tie winner is not the
proposed contract: production change capture requires complete per-key order,
consistent upsert/delete comparisons and defined duplicate/conflict handling.

**Limits.** No watermark generator, integrated change-capture operator,
sliding windows, joins or executed state reclamation. The proposed cleanup
rule must retain state needed by incomplete effects. Rename alone does not
establish power-loss durability. Full snapshots, high-cardinality state and
whole-batch reduction have no measured memory or throughput envelope.

## What the set establishes

The prototypes provide evidence for in-process marker transport, controlled
alignment, single-file-sink recovery, separate Delta transaction options,
Iggy range validation and recorded-state restoration.

They do not establish a complete exactly-once protocol. Prepared boundaries,
partial effects, stable recovery identity, durable publication, replay
ordering and reclamation must be settled together. Neither production
planner wiring nor the Spark end-to-end replacement exists. Passing these
component cases does not resolve the uncovered failure schedules above.

## Additional upstream foundation probes

Focused Rust probes compiled eight unchanged source/build/protobuf files from
upstream Sail `85c6cca01`, with its resolved Arrow 59.2.0 and DataFusion 55.2.0
dependency versions. They exercise real event encoding, placeholders and
DataFusion expression/filter calls in an isolated harness.

| Executed check | Result |
| --- | --- |
| Zero-column data and all four marker kinds | Encoding succeeds; decoding fails without a preserved row count |
| Nonnullable decimal fields across all four widths | Nondefault precision/scale produces marker type mismatches |
| Strict casts and the rewritten predicate shape on markers | Placeholder evaluation fails before marker handling can protect it |
| Schema-level metadata | Encoding drops the map |

Twenty-nine expected error cases reproduced, with success controls for ordinary
rows, nonempty schemas and valid decimal configurations. Metadata loss was a
separate assertion. The successful harness exit confirms reproduction of defects;
it does not indicate that the foundation passed its correctness requirements.
These are component tests, not Sail SQL, distributed execution or storage tests.

## Required evidence beyond these prototypes

The reviewed execution transport still needs graph-wide marker alignment and
bounded-memory qualification. The append sink buffers an interval, snapshots
rewrite complete state and local replica overflow can grow without bound.
No throughput or resource envelope follows from the recorded cases.

Every durable target needs commit-time fencing, including creation, managed
Delta, Iceberg and worker execution. The bounded reference runtime’s exact-byte
Delta ratification is reusable but does not qualify those other paths. Source
inspection identifies the gaps; no new storage takeover tests ran here.

The replacement needs fixed prepared identities, evaluate-once validation,
current-version conflict checks, real crash recovery and explicit migration.
A small independent Python model verifies grouping counterexamples for Spark’s
rules and consistent maxima for valid complete orders. It is a semantic model,
not an engine or durability test. The ordinary source-to-table path, streaming
change-capture merge and distributed recovery remain unbuilt.

## Code versions for the reported mechanisms

| Experiments | Code reference | Comparison scope |
| --- | --- | --- |
| Checkpoint transport, append sink and recorded-state recovery | `4fad33ca5` | Changes over Sail `62251e0a2` |
| Iggy source | `ef5f848a7` | The source commit only; its parent includes additional integration changes |

The references identify experimental implementations, not merged Sail
capabilities. The descriptions above include the tested behavior and its
limits without requiring access to those implementations.
