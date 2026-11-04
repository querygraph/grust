# What the streaming prototypes establish

Four local prototypes exercise Sail's flow events, which carry data batches
and ordered control markers. Their historical test results are preserved
below. This revision inspected source and corrected the scope of the claims;
it did not rerun the Rust, Spark or broker tests.

P1, P2 and P4 are stacked at `4fad33ca5` over upstream `62251e0a2`. P3 is
`ef5f848a7` on integration ancestry and is reviewed as its own commit. The
original report was imported from document commit `32f858e8`. These branches
remain local and unpushed.

## P1 Checkpoint markers and alignment

**Question.** Can a coordinator request checkpoint markers, collect source
positions and finish a bounded query through the existing event model?

**Historical result.** The test-driven, in-process coordinator records
positions in memory. A merge aligns equal checkpoint identifiers across
inputs. Controlled runs combine watermarks and finish after end of data and
a checkpoint. The rate source's position is a row counter for exercising the
protocol; it does not make time-dependent rate rows replayable.

| Reported test | Historical passes |
| --- | --- |
| Two rate sources unioned, filtered, merged and collected | 20 of 20 |
| Marker order from four partitions | 20 of 20 |
| Watermark combination over three inputs | 20 of 20 |

**Decision evidence.** A coordinator can exercise these mechanisms in local
mode without introducing a driver. Its production owner remains S1's choice.

**Limits.** No durable coordinator, cluster transport or recovery test.
Source review found that end and close can count the same input twice, and
that overlapping checkpoint requests can strand different inputs at
different barriers. The reported schedules do not exercise these cases.
These findings remain unexecuted in this review.

## P2 Tagged append and separate Delta writes

**Question.** Can an append sink recover both sides of a commit crash window?

**Historical result.** A replayable test source feeds one file-table sink.
Positions are recorded before the sink commits. The harness simulates a
crash by aborting the reader task and retaining positions in memory. An
interruption after commit resumes from that checkpoint; one before commit
replays from the previous one.
The harness can reuse an uncommitted identifier at a new boundary only
because its sole sink has not committed it.

A separate Delta prototype implements the application identifier and
transaction version options for idempotent writes. Its tests exercise those
options directly; they are not an integrated Delta streaming-restart test.

| Reported test | Historical passes |
| --- | --- |
| File sink simulated crash after commit | 20 of 20 |
| File sink simulated crash before commit | 20 of 20 |
| Delta idempotent-write cases on Sail | 9 of 9 |
| Same cases on Spark 4.2.1 with Delta 4.4.1 | 9 of 9 |

**Decision evidence.** Recording positions before a commit is necessary.
It is not sufficient for several sinks or the two change-capture effects.
Reusing an identifier at a different boundary can skip rows in an already
committed sink. S6 now asks which recovery scope to support.

**Limits.** No integrated Delta checkpoint sink, multiple-sink crash test,
change-capture merge, retractions or other table formats. A source-path
inference identifies a possible duplicate write when two plans see an absent
Delta table and use the same transaction identity. Reproduce that path before
extracting a standalone implementation PR.

## P3 Iggy positions and exact-range reads

**Question.** Can an Iggy source resume while detecting retained-data gaps
and partition recreation?

**Historical result.** Reads use the bounded adapter's exact-range reader.
Positions contain the next offset and partition incarnation. The reported
cases detect a resume below retention and recreation before scanning.

| Reported broker test | Historical result |
| --- | --- |
| Bounded run reads each message once | Pass |
| Resume reads each new message once | Pass |
| Resume below retained data fails | Pass |
| Resume onto a recreated partition fails | Pass |
| These cases repeated on idle cores | 20 of 20 |
| These cases repeated with all cores saturated | 15 of 15 |

The original report also records retention overtaking a resume during a run,
which the exact-range check caught. It records that stream termination can
precede coordinator completion.

**Decision evidence.** Source completion and durable run completion need
separate accounting. Incarnation belongs in every recoverable position.

**Limits.** Source review found a gap when a partition is recreated between
scan and bounding: end-of-data can precede the incarnation check. Bound
capture racing ongoing consumption also needs a controlled test. These cases
were not rerun. Planner registration and upstream dependency alignment remain
outside the prototype.

## P4 Recorded window state and interval reduction

**Question.** Can a window operator snapshot and restore state for a recorded
event sequence?

**Historical result.** A tumbling window counts and sums per key. Recorded
watermark markers close windows and determine the late-row count. Each
checkpoint writes the full open state as an Arrow segment and then its
manifest, using rename. Recovery reads the requested checkpoint and refuses
incompatible column types. A separate function reduces an already collected
batch of change rows, resolving ties by its row order and retaining deletes
with sequence values.

| Reported test | Historical passes |
| --- | --- |
| Windows and late count on recorded input | 20 of 20 |
| Restart reproduces remaining output and final state | 20 of 20 |
| Snapshot under another key type is refused | 20 of 20 |
| Interval reduction with a tie and a delete | 20 of 20 |

The original report states that disabling restore fails the restart and
schema-refusal tests. That control was not rerun here.

**Decision evidence.** File snapshots support recovery for that fixed merged
event order. They do not prove recovery under another source interleaving.
The tie test proves recorded row order, not a total source-position order.

**Limits.** No watermark generator, integrated change-capture operator,
sliding windows, joins or executed state reclamation. The proposed cleanup
rule must retain state needed by incomplete effects. Rename alone does not
establish power-loss durability. Full snapshots, high-cardinality state and
whole-batch reduction have no measured memory or throughput envelope.

## What the set establishes

The prototypes provide evidence for in-process marker transport, controlled
alignment, single-file-sink recovery, separate Delta transaction options,
Iggy range validation and recorded-state restoration. They give maintainers
concrete mechanisms to discuss.

They do not establish a complete exactly-once protocol. Prepared boundaries,
partial effects, stable recovery identity, durable publication, replay
ordering and reclamation must be settled together. Neither production
planner wiring nor the Spark end-to-end replacement exists. Historical pass
counts do not close the source-review findings in ASTRA-REDESIGN-1.

The next deliverable is the discussion packet. Any further experiment should
answer one of its open decisions rather than expand the production design
without a maintainer answer.
