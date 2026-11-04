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
A **continuous run**, which Spark also offers, is the same plan without a fixed
end position. Nothing in the pipeline layer needs to know which of the two it
is running.

An **AutoCDC flow** is a stream source of change rows, an operator that keeps
the latest row per key by sequence number and emits the previous row as a
retraction when a newer one arrives, and a sink that applies inserts and
retractions to the target as merges. The retraction flag is the natural carrier
for "this key's old version is gone", so the model expresses change capture
without a separate changelog type.

## What has to exist

Five pieces, in the order they can land and be tested alone.

**1. Checkpoint coordination.** A run owns a **checkpoint coordinator** that
decides when a checkpoint starts (on a period, or once at the end for a
bounded run) and tells every source to emit the checkpoint marker with the
next id. An operator with state snapshots that state when the marker has
arrived on all its inputs, then forwards the marker. A sink **commits** when the
marker arrives: it makes the rows it received since the previous marker
durable under the checkpoint id, records the id, and acknowledges. The
coordinator records each source's position for that id. A restart resumes
every source from the positions of the last acknowledged checkpoint, and a sink
that sees an id it already committed skips it. This gives each row exactly one
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
A **key-latest** operator keeps, per key, the row with the highest sequence
value seen, emits a retraction of the previous row and the new row when a
newer one arrives, and is what AutoCDC needs. A **deduplicate** operator keeps
the set of keys seen within the watermark horizon and drops repeats. Each
snapshots its state at checkpoints to the run's state store. The state store is
a directory per run under the pipeline's checkpoint location, with one
immutable segment per checkpoint and a manifest naming the segments that make
up the current state, so recovery is a read of the manifest. Stream-to-stream
joins are deliberately left out of the first version; they are the largest
state machine and Spark's own semantics for them in pipelines are the least
used.

**5. A merge sink for change capture.** A sink that collects inserts and
retractions between checkpoints and, at the marker, applies them to the target
as one merge: delete the retracted keys' rows, insert the new rows, in one
transaction tagged with the checkpoint id. Targets without transactions (Hive
file tables) are written by replacing the affected partitions, which is what
Spark does for them too. Where two runs could write one target, a lease in a
small control store prevents the second from committing; that store exists
already for the batch kinds and is not changed here.

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
Spark evaluates stateful queries by difference between microbatches, which
ties results to batch boundaries the user never chose. Here state lives in
operators and advances continuously, so the same query over the same input
produces the same final table regardless of where checkpoints fall. Spark
sorts late rows by a per-batch watermark; here the watermark is a marker in
the stream and a row is late or not by the same rule at every operator.

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
