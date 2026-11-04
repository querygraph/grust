# Streaming tables and change capture on Sail's continuous streaming model

A proposal for Sail's maintainers. Status: draft for discussion, 2026-11-04.

## What this is

Spark Declarative Pipelines lets a user declare tables and views in Python or
SQL and have the engine compute them in dependency order. Two of its dataset
kinds consume data incrementally: a **streaming table**, which appends each new
input row to a target table exactly once, and an **AutoCDC flow**, which applies
a stream of change rows (inserts, updates, deletes keyed by a primary key and
ordered by a sequence column) to a target table so that it always holds the
latest version of each key. Sail already runs the batch kinds of the same
pipelines. This document proposes how the two incremental kinds should run on
Sail's existing continuous streaming model, which we call the flow-event model
below, instead of on bounded microbatches.

It is not a proposal to change the flow-event model's contracts. It adds a
source, a few operators, two sinks and a coordinator that the model already
leaves room for, and names the places where the model needs a decision that
only its owners can make.

## The model we build on

Sail's streaming model, in `crates/sail-common-datafusion/src/streaming`, has
four parts that this proposal relies on.

A **stream source** is a table provider whose scan returns an unbounded
execution plan. Its output rows are **flow events**: either a batch of data
rows with a per-row **retraction flag** (a retracted row cancels an earlier row
with the same values), or a **marker**. The four marker kinds are a latency
tracker, a **watermark** (no later data row will carry an event time older than
the watermark's timestamp), a **checkpoint** with a numeric id (every source
emits it to start a new checkpoint), and **end of data** (the stream will carry
no more data rows but stays open until the next checkpoint completes). Flow
events are encoded into ordinary Arrow batches with two leading columns, so
they pass through any operator that forwards columns it does not know.

A **rewriter** turns a batch logical plan into a streaming one: table scans of
stream sources become their scans, batch inputs are adapted by emitting their
rows and then end of data, projections and filters and limits become streaming
variants, and a plan with no sink gets a **collector** that returns results once
the input is bounded. Windows, aggregates, joins, sorts and repartitions are
refused today. No source emits checkpoint or watermark markers yet, and no
component consumes them.

## The two kinds, restated in the model

A **streaming table** is a stream source (or several, through a union) followed
by stateless operators, or by an event-time window aggregate, ending in a sink
that appends to a table. A **run** of a pipeline must process everything the
sources hold at the moment the run starts and then finish; this is Spark's
"available now" semantics. In the model this is exactly end of data: at run
start the source fixes its end position, emits its rows up to that position,
then the end-of-data marker, and the sink finishes after the next checkpoint.
This is not an addition to the model: its end-of-data marker is documented
as "the stream will contain no more data events" with the sink waiting for
the next checkpoint marker before the job finishes, which is a run that ends.
Spark's pipelines have no other mode: every streaming flow in a run uses the
available-now trigger and the run returns when its flows complete. A
**continuous run**, the same plan with no fixed end position and periodic
checkpoints, is therefore a Sail capability beyond Spark's pipelines, not a
compatibility requirement; the coordinator serves it because Sail's existing
streaming queries, started through the Spark streaming API, are continuous
already.

An **AutoCDC flow** is a stream source of change rows, each an upsert or a
delete of one key ordered by a **sequence** value, an operator that reduces
the rows of one checkpoint interval to one row per key, and a sink that
merges those rows into the target. Ordering across intervals does not live in
the operator: as in Spark, it lives in the target itself, in a metadata
column that records per row the sequence of its last upsert and last delete,
and in an **auxiliary table** beside the target that holds **tombstones**, the
records that a key was deleted at a given sequence so that an older upsert
arriving later does not bring it back. A delete is therefore a durable fact
with its own sequence, not a retraction of an earlier row, and the model's
retraction flag is not used for change capture.

## What has to exist

Five pieces, in the order they can land and be tested alone.

**1. Checkpoint coordination.** A run owns a **checkpoint coordinator**,
held by the job runner (in process in local mode, where no driver exists;
delegated to the driver in cluster mode, where it reaches each source through
the task that runs its partition), that decides when a checkpoint starts (on a period, or once at the end for a
bounded run) and tells every source to emit the checkpoint marker with the
next id. An operator with state snapshots that state when the marker has
arrived on all its inputs, then forwards the marker. When the marker arrives at a sink, the coordinator first records each
source's position for that id durably; only then does the sink **commit**:
it makes the rows it received since the previous marker durable under the
checkpoint id, records the id, and acknowledges. A restart resumes every
source from the positions of the last checkpoint the sinks hold (the least
committed id among several sinks), and a sink that sees an id it already
committed skips it. The order is what makes each row count once: a commit
before the positions were recorded would let a restart reissue the id at a
different boundary and skip rows. This gives each row exactly one
effect on the target. The alignment rule (wait for the marker on all inputs)
is the only new protocol; it is the standard barrier scheme and needs no
change to the marker format.

**2. A table append sink.** A sink that buffers data rows between checkpoints
and, at the marker, writes them as one transactional append to the target
table (Delta and Iceberg have transactions; file tables use a staged directory
renamed at commit), tagging the commit with the checkpoint id. It ignores
retractions, since a streaming table's input is append-only by Spark's
definition, and fails the run if it receives one.

**3. A message-broker source: Apache Iggy.** Iggy is a message broker with
streams, topics and partitions; each message has a monotonically increasing
offset within its partition. The source reads a topic as flow events: a batch
of decoded messages per poll, a watermark derived from the message
timestamps when the user declares an event-time column, the checkpoint marker
when the coordinator asks for it, and end of data when a bounded run reaches
the offsets observed at start. Its position for a checkpoint is one offset per
partition. A partition whose retained offsets no longer cover the recorded
position fails the run rather than silently skipping; so does a partition that
was recreated. This source is the only one that needs the broker's client
library; it lives in its own optional crate so that a default build of Sail
carries no broker dependency.

**4. Three stateful operators.** A **windowed aggregate** groups rows by an
event-time window and a key, holds partial results until the watermark passes
the window's end, then emits the window's result and drops its state; late
rows, with event time below the watermark at arrival, are dropped and counted.
An **interval-reduce** operator, for change capture, keeps per key the row
with the highest sequence seen since the last checkpoint marker, emits those
winners and the deletes with their sequences at the marker, and then holds
nothing: it never remembers a key across intervals, because the target does.
Equal sequences are resolved by a stated rule, source position, so that a
replay picks the same winner; Spark leaves the tie undefined, and this is
recorded as a deliberate difference. A **deduplicate** operator keeps the set
of keys seen within the watermark horizon and drops repeats. The windowed and
deduplicate operators snapshot their state at checkpoints to the run's state
store: a directory per run under the pipeline's checkpoint location, with one
immutable segment per checkpoint per operator and one manifest per recorded
checkpoint. Recovery reads the manifest of the checkpoint the run resumes
from, never the newest one, since an operator may have written state for a
checkpoint the coordinator never recorded; segments are deleted only after a
later checkpoint is recorded; a snapshot is read back only under the column
types it was written with; and an operator whose state shrinks rewrites it as
one compacted segment. Stream-to-stream joins are deliberately left out of the
first version; they are the largest state machine and Spark's own semantics
for them in pipelines are the least used.

**5. A merge sink for change capture.** A sink that takes the interval's
reduced rows at the marker, seals them so that every retry reads the same
winners, and applies them as Spark does: first a merge into the auxiliary
table, which advances or removes tombstones, then a merge into the target,
whose conditions compare each incoming sequence with the sequences in the
metadata column. Both commits carry the checkpoint id, and the checkpoint
counts as committed only when both tables carry it. The four tombstone rules
Spark pins are kept: a delete older than the stored upsert leaves the row but
records a tombstone; a delete that loses to an upsert in the same interval
records none; an upsert at or above a tombstone's sequence removes it; an
upsert below the stored sequence is ignored. The sink reads the key columns
recorded on the auxiliary table before its first commit and refuses a run
whose keys differ; only a full refresh changes them. A target without
row-level operations, such as a Hive file table, is refused as Spark refuses
it. Where two runs could write one target that no catalog manages, a lease in
the existing control store fences them: a commit carries the lease's epoch
and the table refuses an older epoch, and a run that starts after a crash
waits out the dead owner's lease and takes over. Targets a catalog manages
run without that fence, as recorded in the batch design.

**Watermarks and full refresh, across the pieces.** A watermark is declared
on a dataset and may follow filters, projections and renames, so it is a plan
operator placed where the user declared it, emitting the watermark marker from
the rows that reach it; it is not a source property. A row is late only when
every window it belongs to has ended at or before the watermark, so a row
behind the watermark still updates an open window. An operator with several
inputs takes the minimum of their watermarks, never moving back, in whole
milliseconds, and the checkpoint records that combined value only; after a
restart each declared watermark counts again from the new run's rows. A full
refresh of a change-capture flow discards positions and operator state,
replaces the target's schema and keys, empties the auxiliary table, and
reprocesses the source from its origin; a source that no longer holds its
origin refuses the refresh rather than rebuild a target missing its oldest
changes.

## What changes for the pipeline layer

The pipeline layer, in `crates/sail-spark-connect/src/pipelines`, keeps its
registration, analysis and scheduling as they are. For an incremental dataset
it builds a streaming plan through the rewriter instead of looping over
bounded batches, starts it as a streaming query under the session's existing
streaming-query manager, and waits for it to finish (bounded run) or leaves it
running (continuous run). The bounded-batch path and its own source
abstraction are removed, not kept beside the new one. The analysis-time
refusals stay: a streaming table over an unsupported operator is refused with
the operator's name before any run, as Spark refuses it.

## What this does not do

It does not change the flow-event encoding, the marker set or the rewriter's
contract. It does not add a second streaming engine or a scheduler. It does
not claim parity with Spark's full Structured Streaming operator set; the three
operators above are the ones Spark's pipeline tests exercise. It does not
decide the checkpoint period for continuous runs, nor whether the coordinator
lives in the session or in the execution driver; both are questions below.

## Where this is deliberately not Spark

Sail matches Spark's intended behavior and replaces Spark's inconsistencies
with consistent behavior where correctness allows; it does not reproduce
choices that exist only because of Spark's microbatch engine.

Spark lets a stopped run leave a streaming table's last microbatch partly
written and reconciles it from its own log on the next start. Here a
checkpoint is the only unit of durability, so a stopped run leaves the target
exactly at its last acknowledged checkpoint and nothing has to be reconciled.
Spark applies the watermark computed at the end of one microbatch to the
next, so a row arriving in the same microbatch as the row that advanced the
watermark is never late; here the marker advances as rows arrive, so such a
row can be late. This difference is observable, several of the ported Spark
tests assert the microbatch outcome, and it is kept as a deliberate
difference with its tests marked. Spark leaves undefined which of two change
rows with equal key and sequence wins within a microbatch; here the rule is
stated and deterministic, so a replay cannot change the winner.

**Recovery and re-reading.** A restart re-reads rows between the recorded
positions and the sinks' committed tags. A re-read is not always identical to
the first read: a broker may have dropped retained messages, a view may hold
a non-deterministic expression. For change capture, therefore, the sealed
reduced rows of each checkpoint are archived before the merges and restored
on recovery, as the current runtime does; for streaming tables, a flow whose
re-read is not guaranteed identical is refused at analysis with the reason
named.

## What was verified, and how

Against the Spark 4.2.1 source: the pipeline graph executor starts every
streaming flow with the available-now trigger
(`sql/pipelines/.../graph/TriggeredGraphExecution.scala`), and the pipeline
command protocol offers a dry-run flag and refresh selections but no
continuous mode (`spark/connect/pipelines.proto`); the installed client's
`spark-pipelines run` has only refresh options. Against Sail's `main`: the
four marker kinds and the end-of-data semantics are in
`crates/sail-common-datafusion/src/streaming/event/marker.rs`, unchanged
since the streaming events were introduced; no source emits checkpoint or
watermark markers and the rewriter refuses windows, aggregates, joins and
repartitions (`crates/sail-plan/src/streaming/rewriter.rs`). Both were read
from source; nothing here was run. The uncertainty that remains is how the
maintainers intend checkpoints to be coordinated, which is the first
question below.

## Questions for the maintainers

1. Where should the checkpoint coordinator live: in the session, next to the
   streaming-query manager, or in the execution driver, which already owns
   job and task state? The driver placement makes distributed runs natural;
   the session placement is simpler for local mode.
2. Should a source's checkpoint position be part of the stream-source trait
   (a method the coordinator calls), or should the coordinator keep positions
   through a separate interface that only checkpointable sources implement?
   The second keeps the rate and socket sources unchanged.
3. Is a per-run state directory with immutable segments and a manifest the
   state store you would accept, or do you have a preferred store?
4. The windowed aggregate drops late rows; Spark offers an allowed lateness.
   Should the first version expose it?

## How it would be built

In the order above, each piece with its own tests: the coordinator with the
rate source (which gains checkpoint markers) and the collector; the append
sink with a file table; the Iggy source against a pinned broker; the operators
against recorded inputs with known outputs; the merge sink against Delta and
Iceberg. Then the pipeline layer switches over and the ported Spark pipeline
tests for streaming tables and AutoCDC run again. We would build the first
piece after this document is discussed, not before.
