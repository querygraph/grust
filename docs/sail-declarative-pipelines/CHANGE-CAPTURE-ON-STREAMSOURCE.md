# Change capture on Sail's flow event model

Change capture applies keyed updates and deletes to a table in sequence
order. It lets a pipeline maintain current records even when older changes
arrive later. This proposal maps that behavior to Sail's existing stream
sources and ordered control markers.

It does not propose keeping the whole target in operator state or treating
a delete as a retraction that cancels an earlier emitted row. The initial
scope remains open: include recoverable change capture, or deliver append
streaming first.

## Fit with Sail

Sail's `StreamSource` provides a streaming scan. It emits flow events: data
batches and ordered control markers. A checkpoint marker identifies a
boundary at which source positions and operator state can be saved. An
end-of-data marker says a source reached its bounded end; the run still
needs to finish its writes. These existing concepts are the foundation,
rather than a second engine that repeatedly executes bounded queries.

The proposed additions are source checkpoint participation, coordination,
row validation, reduction between checkpoint markers, and a sink that merges
into two tables. A durable checkpoint record must connect source progress
to those table effects. Marker transport and row reduction have component
experiments, but the coordinated change-capture path remains unbuilt.

## Preserve the change semantics

A change row contains a key, a sequence value for ordering, and an action.
An upsert inserts or updates that key; a delete removes it.
Spark 4.2.1 validates the original input rows, reduces each batch to one
winner per key, then merges into an auxiliary table and the target. The
auxiliary table retains tombstones, records of deletion sequences that stop
older changes from bringing deleted keys back. Target metadata preserves
ordering for live rows. The
[batch handler](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1ForeachBatchHandler.scala#L39)
shows that order.

The sequence comparisons matter. An upsert at an equal or greater sequence
can replace the current target row; a delete removes it only at a strictly
greater sequence. A tombstone rejects strictly older events. An upsert at or
above its sequence removes the tombstone. A delete that loses during
reduction reaches neither merge. These are separate rules from choosing
between equal-sequence rows within a batch. The
[merge processor](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L220)
contains those comparisons.

We propose reducing the rows between successive checkpoint markers to one
winner per key. The reducer emits those winners at the marker, then clears
its interval state. Deletes retain their sequence values. Ordering across
intervals remains in the tables rather than an unbounded copy of every target
key in the operator. The existing local experiment is only a whole-batch
reduction function, not this streaming operator.

## Validate before reduction

Every original row must pass validation before either table effect begins.
A losing invalid row must still fail the interval. Spark rejects null
sequence values, null values in each declared key column and non-orderable
sequence types. It does not recursively reject every null field inside a
non-null struct value. See the
[validator](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/ScdBatchValidator.scala#L45).

The proposed reducer can validate as it consumes rows, or consume input with
validation evidence covering the same rows. A validation receipt would name
the interval and contract that were checked. The contract identifies the
schema and computation that give those rows meaning. How to persist and
verify that identity belongs to the recovery decision. Validation of winners
alone cannot preserve the original-row guarantee.

## Decide recovery for two effects

A flow is one declared computation feeding a target. One change-capture
flow still has two table effects. A crash after the auxiliary merge but
before the target merge leaves a partially completed checkpoint. A shared
identifier alone neither completes the second effect nor defines its rows.
Spark's inspected merge calls use sequence comparisons for replay safety;
they do not attach the batch identifier as a transaction tag.

We recommend sealing the reduced rows before the first effect. Sealing means
persisting the selected rows as an immutable artifact that every retry reads.
The prepared checkpoint would bind that artifact to source boundaries,
validation evidence, the flow contract and each table's completion record.
This is a proposed Sail recovery mechanism, not a claim about Spark's
checkpoint implementation.

There are two useful choices. Include change capture initially with durable
sealed rows and separate effect completion, or ship append-only streaming
first and defer this protocol. Rereading without an archive is another
possible tradeoff only if the design proves identical inputs and transformed
rows remain available until all pending effects finish. Source positions
alone do not provide that proof.

Recovery should finish pending effects from their sealed input before
advancing to new boundaries. Source retention must still be checked for
subsequent unread data. An archive does not make the broker's entire future
history available. Atomic visibility across both tables is outside this
proposal's guarantee.

## Keys, refresh and writer ownership

Spark checks existing key names and types as a set under the session's name
resolver. Reordering the declaration alone is accepted. A full refresh
rebuilds the target from source data under a new recovery identity, called a
checkpoint generation. It truncates the target, drops its auxiliary table and
adopts the current output schema. The
[key check](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowExecution.scala#L514)
and
[refresh path](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/DatasetManager.scala#L301)
establish those behaviors.

We propose keeping those checks and explicitly separating recovery identities
across full refreshes. Requiring a source to retain its absolute origin would
be a further Sail admission policy. Spark's table-reset path does not prove
that policy for every connector. Source options and retained history must be
part of the refresh decision before destructive effects begin.

Targets must support row-level operations. Writer ownership can be protected
by giving each new owner a greater epoch, an ownership number. A target's
fence rejects writes carrying an older epoch. Replacing a fenced write
path must preserve that protection. Whether other targets need that
mechanism remains open. A catalog ordering individual commits does not
establish ownership across both table effects.

## Differences that need a decision

Spark leaves equal-key, equal-sequence winners within a batch undefined.
A fixed total order over source positions would change that contract and
would need a definition across partitions and transformations. The reduction
experiment selects the later row in recorded input order; asynchronous replay
can change that order.

We recommend guaranteeing that sealed winners remain unchanged during
recovery, while leaving the initial equal-sequence choice undefined. If a
stronger ordering is wanted, define and test it separately. Archives,
validation receipts and ownership fences also require Sail-specific evidence;
they are not covered by a blanket claim of Spark parity.

## Evidence and questions

The Spark 4.2.1 claims above are supported by pinned source inspection of
validation, sequence comparisons, merge order, key drift and refresh behavior.
Reduction tests cover a tie and a delete in recorded rows, not streaming
intervals or cross-partition replay. The merge sink, durable checkpoint record
and end-to-end replacement remain unbuilt. No integrated Spark comparison
establishes compatibility of that replacement.

Should change capture be included in the initial recovery scope? If so, is
sealed input with separate effect completion the acceptable starting point?
Should equal-sequence selection stay undefined before sealing? These answers
determine the recovery protocol to test. Its decisive experiment must crash
between the two merges and finish both effects from the same validated rows.
