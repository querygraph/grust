# Review of the streaming redesign against the current AutoCDC runtime

This review checks the streaming proposal, its decision notes, the architecture
overview and the prototype specifications against what the current AutoCDC
runtime guarantees and what its tests pin against Spark 4.2.1. The current
runtime is the bounded-microbatch implementation on the integration branch;
its behavior is the reference for what a reader of the new design may assume
is kept. Findings name the document and section they apply to.

Terms used below. An **AutoCDC flow** applies change rows, each an upsert or a
delete of one key ordered by a **sequence** value, to a target table. A
**tombstone** is the record that a key was deleted at a given sequence, kept so
that an older upsert arriving later does not bring the key back. The
**auxiliary table** is the table Spark 4.2.1 creates beside every AutoCDC
target to hold those tombstones. The **metadata column** is the column Spark
4.2.1 writes into the target to record, per row, the sequence of its last
upsert and of its last delete.

## Claims the current runtime shows to be wrong or incomplete

**Change capture has no per-key operator state in Spark, and should not have it
here.** The proposal, "What has to exist", piece 4, and the architecture,
"Data flow for change capture", describe a key-latest operator that keeps the
latest row of every key in operator state. Spark 4.2.1 keeps no such state.
Each microbatch is reduced to one row per key and merged twice: once into the
auxiliary table, which advances or removes tombstones, and once into the
target, where the merge conditions compare the incoming sequence with the
sequences stored in the target's metadata column. The ordering lives in the
target. An operator that remembers every key ever seen duplicates the target,
grows without bound, and must be recovered on restart, which the current
design never has to do. The recommendation is that the operator reduce only
within one checkpoint interval and that ordering across intervals stay in the
two merges.

**Deletes are not retractions.** The proposal, "The two kinds, restated in the
model", says the retraction flag carries "this key's old version is gone". A
delete in AutoCDC is a durable fact with its own sequence, not the withdrawal
of an earlier row. The current tests pin four consequences on Spark 4.2.1: a
delete older than the stored upsert leaves the row and still records a
tombstone; a delete that loses to an upsert in the same microbatch records no
tombstone; an upsert at or above a tombstone's sequence removes the tombstone;
an upsert below the stored sequence is ignored. None of these is expressible
as a retraction of a previous row, because the previous row may never have
been seen by this run. The merge sink needs the delete and its sequence, not a
retraction.

**The merge is two commits, not one.** The proposal, piece 5, and the
architecture, "Data flow for change capture", describe one merge in one
transaction. Spark 4.2.1 writes the auxiliary table and the target in two
merges, and a crash between them leaves tombstones and rows disagreeing. The
current runtime seals the reduced rows once, so that both merges read the same
winners, and records both outcomes before either is acknowledged. The
checkpoint tag scheme in decision note S6 must therefore tag both tables and
treat a checkpoint as committed only when both carry the tag.

**Ties between equal sequences need a rule that survives replay.** The
proposal, piece 4, says the operator keeps "the row with the highest sequence
value seen" and says nothing about equal values. Spark 4.2.1 reduces a
microbatch with a maximum-by aggregate, so which of two rows with the same key
and sequence wins inside one microbatch is not defined. Across microbatches the
target merge updates on a sequence at or above the stored one, so the later
arrival wins. The current runtime seals the reduced rows so that every retry
uses the same winner. Under the new design a replay after a crash re-reads the
rows and can choose a different winner unless the rule is deterministic, for
example by source position, which would break the exactly-once claim in the
architecture's "Recovery" section. The rule should be stated, and it is a
deliberate difference from Spark if it fixes what Spark leaves undefined.

**Key drift is refused, and the design must keep refusing it.** None of the
documents mentions a change of key columns. Spark 4.2.1 records the key column
names in a property of the auxiliary table when it is created and refuses a
later run whose keys differ, naming the stored and the requested keys; only a
full refresh changes them. Reordering a composite key is not drift. The type
of the sequence expression fixes the type of the metadata column, and a
sequence of a type that cannot be ordered is refused before any merge. The
merge sink must read the stored keys before its first commit, not discover the
mismatch at merge time.

**Full refresh is missing.** None of the documents says what a full refresh
does to a change-capture flow. Spark 4.2.1 replaces the target's schema and
keys, empties the auxiliary table and reprocesses the source from its origin.
The current runtime refuses a full refresh when the source no longer holds its
first rows, through the bounded source's retained-origin check, rather than
rebuilding a target that silently lacks the oldest changes. The new design
needs a full-refresh path that discards positions and operator state, empties
both tables, and asks each source whether it still holds its origin.

**The lease waits out a dead owner, and the guarantee is a fence, not a lock.**
The architecture's failure table says a second run on one target "cannot take
the lease and fails before writing". The current runtime does the opposite on
purpose: a run that starts after a crash waits until the dead owner's lease has
expired and then takes over, rather than failing. What protects the target is
that a commit carries the lease's epoch and the table refuses a commit from an
older epoch, so an owner that paused past its lease cannot write after the new
owner has started. The proposal, piece 5, also says the control store "exists
already for the batch kinds"; it exists for durable AutoCDC runs only, and it
fences only Delta targets that no catalog manages. Iceberg, Unity Catalog and
catalog-managed Delta targets run without a fence, a decision recorded with
its reason in the design record.

**Hive file tables are refused, as Spark refuses them.** The proposal, piece 5,
and the architecture say a target without transactions is written by
replacing the affected partitions, "which is what Spark does for them too".
Spark 4.2.1 refuses an AutoCDC target that does not support row-level
operations, with the condition `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE`, and the
current runtime ports that refusal. Partition replacement would be a new
capability, not parity, and would need its own section under deliberate
differences.

**The watermark is a plan operator, not a source property.** Decision note S7
and prototype P3 derive the watermark at the source from a declared event-time
column. In Spark 4.2.1 a watermark is declared on a DataFrame and may follow
filters, projections and renames. The current tests pin that a watermark
follows only the rows that reach it, so rows removed by a filter before the
watermark do not advance it, and that a watermark on a renamed event-time
column still closes windows. The watermark must be an operator in the plan
that emits the marker, placed where the user declared it.

**The late-row rule for windows is the window's end, not the row's time.**
Decision note S7 drops a row "whose event time is below the watermark". Spark
4.2.1 drops a row only when every window it belongs to has ended at or before
the watermark, so a row behind the watermark still changes a window that is
open. The current test of that case would fail under the stated rule.

**Several watermarks combine as a minimum, and only the combined one survives
a restart.** The documents do not say how an operator with several inputs
combines their watermarks. Spark 4.2.1 takes the minimum by default, so a
stream whose rows stop advancing holds the query's watermark back; the result
never moves back and is computed in whole milliseconds. Across a restart Spark
keeps only the query's combined watermark: each declared watermark counts
again from the rows of the new run. The current tests pin both behaviors over
a union with one watermark and with a watermark on each stream. Barrier
alignment in note S4 aligns checkpoints; the same operator also needs this
rule for watermarks, and the checkpoint must record the combined value, not
each input's.

**The claim of identical results regardless of checkpoints needs its
boundary.** The proposal, "Where this is deliberately not Spark", says the same
input produces the same final table wherever checkpoints fall. That holds for
checkpoints. It does not hold for the watermark: Spark 4.2.1 applies the
watermark computed at the end of one microbatch to the next, so a row that
arrives in the same microbatch as the row that advanced the watermark is not
late. A watermark that advances on every poll makes such a row late. That is a
deliberate difference with an observable result, and several Spark tests
assert the microbatch outcome.

**The state store must be read by checkpoint, not by latest.** Decision note S5
says segments older than the last checkpoint are deleted and that recovery is
a manifest read. The current store writes one manifest per recorded progress
point and loads the manifest of the point a run resumes from, because an
operator can write its state for a checkpoint that the coordinator never
records. If recovery read the newest manifest, a crash in that window would
pair new state with old positions and apply the replayed rows twice. Segments
may be deleted only after the coordinator has recorded a later checkpoint. Two
further rules from the current store carry over: a snapshot is read back only
under the column types it was written with, and refused otherwise; and an
operator whose state shrinks, as eviction makes it, rewrites its state as one
compacted segment, since an append of new segments cannot express removal.

**Recovery assumes a replay that the sources may not give.** The
architecture's "Recovery" section re-reads rows between the recorded positions
and lets the sinks skip what their tags cover. The current durable run instead
archives each microbatch's sealed rows before committing and restores them on
recovery. It does so because a re-read can differ from the first read: a
broker may have removed retained messages, a view may contain a
non-deterministic expression, and a tie may resolve differently. The new
design either needs the same archive for change capture, or it must refuse at
analysis any flow whose re-read is not guaranteed identical.

## What the key-latest operator and the merge sink must preserve

The specifications should state each of these, since the current runtime and
its Spark 4.2.1 tests depend on them.

- The auxiliary table, with Spark's name, schema and properties, created
  beside the target and read by users and tests.
- The metadata column in the target, with the sequences of the last upsert
  and the last delete per key.
- The four tombstone rules listed above under deletes.
- Failure before any write when a key or the sequence is null, when the
  sequence has a map type, and when a composite key has a null part, naming
  every column involved.
- Name resolution of keys and sequence under the session's case sensitivity,
  and quoted names with dots or special characters surviving across runs.
- The column selection and the excluded columns fixing the target schema.
- The stored-keys check and the full-refresh path described above.
- One sealed reduction per checkpoint interval, read by both merges and by any
  retry.
- The refusal of targets without row-level operations.
- On fenced targets, the enrollment property, the epoch check at commit, the
  refusal of an ALTER on an enrolled table, and the refusal of a target
  recreated outside the pipeline, which a full refresh adopts.

## Prototype P3: what the Iggy bounded source gives and what it does not

**Reusable as written.** The client wrapper, the payload decoding and its
rule that an undecodable message fails the read rather than advancing past it,
the schema validation done when the source is built, the option parsing, the
format registration, and the identity the source reports for itself. The
pinned-broker test setup also carries over.

**The position must carry the incarnation.** Prototype P3 encodes a position
as one offset per partition. The broker reuses a partition's id when the
partition is recreated and restarts its offsets at zero, so an offset alone
cannot detect the recreation the specification promises to refuse. The
bounded source records an incarnation with every cursor and checks it on
every read. The new position needs the same pair.

**The gap check must run on every poll, not only at resume.** The broker does
not report a read past retained data as an error: it returns rows from the
first retained offset instead. The bounded source compares the first offset of
every reply with the offset it asked for. A continuous source that lags behind
retention meets the same silent skip while running, so the check belongs in
the poll loop. Prototype P3 tests it only at resume.

**Offsets are positions of the next row.** A bounded range is the half-open
interval from its start to its end, read exactly once in offset order, and a
cursor names the next offset to read. The checkpoint position should keep that
convention, so that resuming from it neither repeats nor skips a message.

**Reads never acknowledge.** The bounded source keeps no consumer position at
the broker and turns automatic commits off, so a failed read can be repeated
unchanged and nothing pins the broker's retention. The coordinator then owns
the only record of progress, which is what decision note S2 assumes.

**Not reusable.** The range planner and the bounded scan, which plan one
finite read per partition per microbatch, have no counterpart in a long-lived
poll loop and are replaced.

**The client's dependency floor blocks a build on upstream.** The pinned
client requires newer releases of its HTTP and QUIC dependencies than Sail's
lockfile holds, and a lockfile that satisfies it moves about two hundred
packages. Prototype P3 says it is built on the branch for this reason, but the
specifications' opening says every prototype is a branch from upstream; the
two statements should agree.

## How these findings were checked

Each claim about the current runtime was read from its source on the
integration branch and, where named, from the AutoCDC tests that pass both on
Sail and on Spark 4.2.1 with Delta. Each claim about Spark's behavior is the
behavior those tests pin, read against Spark 4.2.1's source when the tests
were written. The Hive finding rests on the merge-support refusal that the
runtime ports from Spark; it was not rerun for this review.
