# Streaming tables on Sail's continuous streaming model

A proposal for Sail's maintainers. Status: draft for discussion, 2026-11-04.
Change capture, the second incremental dataset kind, has its own document,
CHANGE-CAPTURE-ON-STREAMSOURCE.md, built on the pieces proposed here.

## What this is

Spark Declarative Pipelines lets a user declare tables and views in Python or
SQL and have the engine compute them in dependency order. One of its dataset
kinds consumes data incrementally: a **streaming table** appends each new
input row to a target table exactly once. Sail already runs the batch kinds of
the same pipelines. This document proposes how streaming tables should run on
Sail's existing continuous streaming model, which we call the flow-event model
below, instead of on bounded microbatches.

It is not a proposal to change the flow-event model's contracts. It adds a
source, two operators, a sink and a coordinator that the model already leaves
room for, and names the places where the model needs a decision that only its
owners can make.

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
no more data rows but stays open until the next checkpoint completes). Flow events are encoded into ordinary Arrow batches with two leading
columns.

A **rewriter** turns a batch logical plan into a streaming one: table scans of
stream sources become their scans, batch inputs are adapted by emitting their
rows and then end of data, projections and filters and limits become streaming
variants, and a plan with no sink gets a **collector** that returns results once
the input is bounded. Windows, aggregates, joins, sorts and repartitions are
refused today. No source emits checkpoint or watermark markers yet, and no
component consumes them.

## A streaming table, restated in the model

A streaming table is a stream source (or several, through a union) followed by
stateless operators, or by an event-time window aggregate, ending in a sink
that appends to a table. A **run** of a pipeline must process everything the
sources hold at the moment the run starts and then finish; this is Spark's
"available now" semantics. In the model this is exactly end of data: at run
start the source fixes its end position, emits its rows up to that position,
then the end-of-data marker, and the sink finishes after the next checkpoint.
The model already says this: its end-of-data marker is documented with the
sink waiting for the next checkpoint before the job finishes. Spark's
pipelines have no other mode. A **continuous run**, the same plan with no
fixed end position and periodic checkpoints, is a Sail capability beyond
Spark's pipelines, served because Sail's existing streaming queries are
continuous already.

## What has to exist

Four pieces, in the order they can land and be tested alone.

**1. Checkpoint coordination.** A run owns a **checkpoint coordinator** that
decides when a checkpoint starts (on a period, or once at the end for a
bounded run) and tells every source to emit the checkpoint marker with the
next id. It is held by the query's job runner: in process in local mode,
where no driver exists; delegated to the driver in cluster mode, where a
source's scan runs on a worker and the coordinator reaches it through the
task that runs its partition. An operator with state snapshots it when the marker has arrived on all its
inputs, then forwards the marker: the standard barrier scheme, with no change
to the marker format. When the marker arrives at a
sink, the coordinator first records each source's position for that id
durably; only then does the sink **commit**: it makes the rows it received
since the previous marker durable under the checkpoint id, records the id, and
acknowledges. A restart resumes every source from the positions of the last
checkpoint the sinks hold (the least committed id among several sinks), and a
sink that sees an id it already committed skips it. The order makes each row count once: a commit before the positions were
recorded would let a restart reissue the id at another boundary and skip
rows. The run is
finished when the coordinator says so, not when the query's stream ends,
because the stream can end as soon as the final marker passes through it.

**2. A table append sink.** A sink that buffers data rows between checkpoints
and, at the marker, writes them as one transactional append to the target
table, tagged with the checkpoint id. On Delta the tag is Delta's own
idempotent-write pair, an application id (the query) and a version (the
checkpoint), so the table itself skips a version it already holds; Iceberg
commits carry the tag as metadata; a file table stages into a directory named
by the checkpoint id and renames it at commit. A retraction is an error,
since a streaming table's input is append-only by Spark's definition.

**3. A message-broker source: Apache Iggy.** Iggy is a message broker with
streams, topics and partitions; each message has a monotonically increasing
offset within its partition. The source reads a topic as flow events: a batch
of decoded messages per poll, the checkpoint marker when the coordinator asks
for it, and end of data when a bounded run reaches the offsets observed at
start. Its position for a checkpoint is, per partition, the next offset to
read paired with the partition's **incarnation**, the identity the broker gives
a partition when it is created, since a recreated partition reuses its id with
offsets from zero. On every poll the source checks that the broker returned
the offset it asked for, because the broker silently skips to the first
retained offset otherwise; a gap or a changed incarnation fails the run with
the partition named rather than silently skipping. Reads never acknowledge at
the broker, so the coordinator owns the only record of progress. This source
is the only one that needs the broker's client library; it lives in its own
optional crate so that a default build of Sail carries no broker dependency.

**4. Two stateful operators and the watermark.** A watermark is declared on a
dataset and may follow filters, projections and renames, so it is a plan
operator placed where the user declared it, emitting the watermark marker
from the rows that reach it; it is not a source property. Where several
inputs merge, the merge forwards the minimum of their watermarks, never
moving back, in whole milliseconds, once each input has sent one, letting an
input that has ended stop holding the minimum back; a downstream operator
sees one combined value, and the checkpoint records that value only. After a
restart each declared watermark counts again from the new run's rows. A
**windowed aggregate** groups rows by an event-time window and a key, holds
partial results until the watermark passes the window's end, then emits the
window's result and drops its state; a row is late, dropped and counted, only
when every window it belongs to has ended at or before the watermark, so a row
behind the watermark still updates an open window; a null event time belongs
to no window. A **deduplicate** operator keeps the set of keys seen within the
watermark horizon and drops repeats. Both snapshot their state at checkpoints
to the run's state store: a directory per run under the pipeline's checkpoint
location, with one immutable segment per checkpoint per operator, written
before its manifest and each by rename, and one manifest per recorded
checkpoint. Recovery reads the manifest of the checkpoint the run resumes
from, never the newest one, since an operator may have written state for a
checkpoint the coordinator never recorded; segments are deleted only after a
later checkpoint is recorded; a snapshot is read back only under the column
types it was written with; and an operator writes one compacted segment per
checkpoint, since appending segments cannot express removal. Stream-to-stream joins are deliberately left out of the first version, as
the largest state machine and the least used in pipelines.

## What changes for the pipeline layer

The pipeline layer, in `crates/sail-spark-connect/src/pipelines`, keeps its
registration, analysis and scheduling as they are. For an incremental dataset
it builds a streaming plan through the rewriter instead of looping over
bounded batches, starts it as a streaming query under the session's existing
streaming-query manager, and waits for the coordinator to finish the run
(bounded) or leaves it running (continuous). The bounded-batch path and its
own source abstraction are removed, not kept beside the new one. The
analysis-time refusals stay: a streaming table over an unsupported operator,
or over a source whose re-read after a restart is not guaranteed identical,
is refused with the reason named before any run.

## What this does not do

It does not change the flow-event encoding, the marker set or the rewriter's
contract. It does not add a second streaming engine or a scheduler. It does
not claim parity with Spark's full Structured Streaming operator set; the two
operators above are the ones Spark's pipeline tests exercise for streaming
tables. It does not decide the checkpoint period for continuous runs.

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
difference with its tests marked.

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
repartitions (`crates/sail-plan/src/streaming/rewriter.rs`); local mode runs
with no driver and cluster scans are rebuilt on workers. Prototypes of pieces
1 to 4, on `main`, pass their tests; their results document says what each
showed.

## Questions for the maintainers

1. Should the checkpoint coordinator be owned by the job runner, in process
   locally and delegated to the driver in cluster mode, as proposed; or should
   local mode gain a driver so that one placement serves both?
2. Should a source's checkpoint position be part of the stream-source trait,
   or a separate interface that only checkpointable sources implement, as
   proposed, which keeps the rate and socket sources unchanged?
3. Is a per-run state directory with immutable segments and a manifest per
   checkpoint the state store you would accept, or do you have a preferred
   store?
4. The windowed aggregate drops late rows; Spark offers an allowed lateness.
   Should the first version expose it?

## How it would be built

In the order above, each piece with its own tests: the coordinator with the
rate source (which gains checkpoint markers) and the collector; the append
sink with a file table and Delta; the Iggy source against a pinned broker;
the operators against recorded inputs with known outputs. Then the pipeline
layer switches over and the ported Spark pipeline tests for streaming tables
run again. Nothing is built for merge before this document is discussed.
