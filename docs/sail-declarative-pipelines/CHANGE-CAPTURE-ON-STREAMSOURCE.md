# Change capture on Sail's continuous streaming model

A proposal for Sail's maintainers, companion to STREAMING-ON-STREAMSOURCE.md,
whose coordinator, state store and watermark rules it uses. Status: draft for
discussion, 2026-11-04.

## What this is

An **AutoCDC flow** in Spark Declarative Pipelines applies a stream of
**change rows** to a target table so that the target always holds the latest
version of each key. A change row is an upsert or a delete of one key,
ordered by a **sequence** value the user names. This document proposes how
such flows run on the flow-event model, with the ordering kept where Spark
keeps it and nothing invented beyond what Spark's own tests pin.

## How Spark keeps order, and why that stays

Spark keeps no per-key operator state for change capture. Each microbatch is
reduced to one row per key and merged twice: into an **auxiliary table**
beside the target, which holds **tombstones**, the records that a key was
deleted at a given sequence so that an older upsert arriving later does not
bring it back; and into the target, whose **metadata column** records per row
the sequence of its last upsert and of its last delete, and whose merge
conditions compare each incoming sequence with those. Ordering across runs
therefore lives in the target and the auxiliary table, not in an operator.
This proposal keeps that shape. An operator that remembered every key would
duplicate the target, grow without bound and need its own recovery; and the
four tombstone rules Spark pins (a delete older than the stored upsert leaves
the row but records a tombstone; a delete that loses to an upsert in the same
interval records none; an upsert at or above a tombstone's sequence removes
it; an upsert below the stored sequence is ignored) need the delete and its
sequence, which a retraction cannot carry. The flow-event model's retraction
flag is not used for change capture.

## What has to exist

**An interval-reduce operator.** Per key, it keeps the row with the highest
sequence seen since the last checkpoint marker, emits those winners and the
deletes with their sequences at the marker, and then holds nothing. Equal
sequences within an interval are resolved by source position, the later row
winning, so that a replay picks the same winner. It keeps no state across
intervals and needs no snapshot.

**A merge sink.** At the marker, the sink seals the interval's reduced rows,
so that every retry reads the same winners, and applies them as Spark does:
first the merge into the auxiliary table, then the merge into the target.
Both commits carry the checkpoint id, and the checkpoint counts as committed
only when both tables carry it; a crash between the two leaves the
checkpoint uncommitted, and the restart restores the sealed rows and reruns
both merges, the auxiliary one idempotent by tag. The sink reads the key
columns recorded on the auxiliary table before its first commit and refuses a
run whose keys differ; only a full refresh changes them. Keys and the sequence
are resolved under the session's case rules; a null key, a null sequence, a
sequence of a type that cannot be ordered, a map-typed sequence or a null
part of a composite key fails before any write, naming the columns. A target
without row-level operations, such as a Hive file table, is refused as Spark
refuses it.

**Recovery that does not trust a re-read.** A restart re-reads rows between
the recorded positions and the committed tags. A re-read is not always the
first read: a broker may have dropped retained messages, a view may hold a
non-deterministic expression. The sealed reduced rows of each checkpoint are
therefore archived before the merges and restored on recovery, so the merges
see the rows the checkpoint saw.

**Full refresh.** A full refresh discards positions and operator state,
replaces the target's schema and keys, empties the auxiliary table, and
reprocesses the source from its origin. A source that no longer holds its
origin refuses the refresh rather than rebuild a target missing its oldest
changes.

**One writer per target, where no catalog orders commits.** Where two runs
could write one Delta target that no catalog manages, a lease in the existing
control store fences them: a commit carries the lease's epoch and the table
refuses an older epoch, and a run that starts after a crash waits out the
dead owner's lease and takes over. Targets a catalog manages run without that
fence, as Spark's own exposure, and the design record states one pipeline per
target as the operator's responsibility.

## Where this is deliberately not Spark

Spark leaves undefined which of two change rows with equal key and sequence
wins within a microbatch, because it reduces with a maximum-by aggregate.
Here the rule is stated and deterministic, so a replay cannot change the
winner; the current implementation already seals the winners for the same
reason. Everything else above matches Spark's behavior as pinned by its
tests on Delta.

## What was verified, and how

The tombstone rules, the key and sequence refusals, the key-drift refusal,
the full-refresh behavior and the lease semantics are the behavior of the
current change-capture runtime on the integration branch, whose tests pass
both on Sail and on Spark 4.2.1 with Delta 4.4.1; the Hive refusal is the
merge-support refusal ported from Spark. The interval reduce was prototyped
on `main` over recorded change rows with a tie and a delete that beats a
later, older-sequence upsert; the merge sink and the archive are not
prototyped yet and are stated from the current runtime.

## Questions for the maintainers

1. Is a deterministic tie rule by source position acceptable as a stated
   difference from Spark, or should ties stay undefined as in Spark?
2. The archive of sealed rows per checkpoint makes recovery independent of
   the source's replay. Would you rather refuse at analysis any
   change-capture flow whose re-read is not guaranteed identical, and keep no
   archive?
3. Should catalog-managed targets gain the lease fence later, or stay on the
   catalog's own commit ordering?

## How it would be built

After the streaming pieces: the interval-reduce operator, then the merge
sink against Delta and Iceberg with the archive, then full refresh, then the
pipeline layer switch, after which the ported Spark change-capture tests run
again. Nothing is built for merge before this document is discussed.
