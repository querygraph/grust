# Decision notes: streaming tables and change capture on the flow-event model

Each note is one post for the maintainers' discussion thread. Context first,
then the options, a recommendation, and what settles it. The proposal they
belong to is STREAMING-ON-STREAMSOURCE.md; the plan is REDESIGN-PLAN.md.

Terms used throughout: a **flow event** is either a batch of rows with a
per-row retraction flag or a **marker**; the markers are latency tracker,
watermark, checkpoint (with an id) and end of data. A **stream source** is a
table provider whose scan yields flow events. A **run** of a pipeline is
bounded when every source fixes an end position at start and emits end of
data on reaching it, and continuous otherwise. A **checkpoint** is a point at
which every source's position and every operator's state are recorded and
every sink's output up to that point is made durable, so that a restart
resumes from it with each row having had exactly one effect.

---

## S1. Where the checkpoint coordinator lives

**Context.** The marker model says each source emits a checkpoint marker "to
start a new checkpoint", but nothing in Sail decides when, assigns the id, or
records the positions. Something must: the coordinator. Two facts about
Sail's execution shape it. Local mode has no driver: the local job runner
executes the plan directly in the session's process. In local-cluster and
Kubernetes modes the cluster job runner starts a driver, and a stream
source's scan does not stay in the driver's process: the plan codec ships the
source's options to a worker, which rebuilds the scan there. A coordinator can
therefore reach a source only through the task that runs its partition.

**Options.**
1. A coordinator per query owned by the job runner: in process for the local
   runner, calling the sources directly; delegated to the driver by the
   cluster runner, which reaches each source through a request to the task
   running its partition and reads the position back in the task's status.
   One interface, two implementations.
2. Driver only, with local mode gaining a driver it does not have today.
3. In the session, next to the streaming-query manager.

**Recommendation.** Option 1. It changes nothing for local execution of
non-streaming queries, keeps the session's streaming-query manager as it is
(query handle, status, stop), and makes the cluster path an implementation of
the same interface rather than a different design. Option 2 would change local
execution for everyone.

**What settles it.** Your preference. Prototype P1 implements the interface
and drives a coordinator in process over two rate sources; the driver-to-task
request of the cluster implementation is the next prototype if you want it
shown before deciding.

---

## S2. How a source takes part in a checkpoint

**Context.** The stream-source trait has `data_schema` and `scan`. A
checkpointing source needs two more things: a way to be told "emit the
checkpoint marker with id N now", and a way to report the position that id
corresponds to. The rate and socket sources have no meaningful position.

**Options.**
1. Add the two methods to the stream-source trait with default
   implementations that do nothing, so every source compiles unchanged.
2. A separate `CheckpointableSource` interface that a source implements only
   if it can checkpoint; the coordinator asks each source for it and treats
   sources without it as having no position.

**Recommendation.** The separate interface. It states which sources can
resume and which cannot, instead of a silent no-op; a pipeline that reads a
non-checkpointable source in a continuous run can be refused at analysis with
the source named. The trait stays as it is.

**What settles it.** Your preference. P1 implements the interface for the
rate source, which gains a counter as its position only to exercise the path.

---

## S3. When a checkpoint starts

**Context.** A bounded run (the only kind Spark's pipelines have: every
streaming flow uses the available-now trigger) needs exactly one checkpoint
at the end so the sink can commit and finish. A continuous run, which Sail's
existing streaming queries already are, needs periodic checkpoints so that a
restart loses little and sinks commit regularly.

**Options.**
1. A fixed period, a run option with a default.
2. A volume trigger: every N rows or bytes across sources.
3. Both, whichever comes first.

**Recommendation.** A fixed period for continuous runs, as a run option, and
one checkpoint at end of data for bounded runs. Volume triggers can be added
later without changing any interface, since the coordinator alone decides.

**What settles it.** Your preference on the default period and on whether the
option lives in the pipeline configuration or the session configuration.

---

## S4. Marker alignment in operators with several inputs

**Context.** A union or a join receives the checkpoint marker with id N from
each input at different times. The operator's state at the checkpoint must
reflect every input up to its marker and nothing after.

**Options.**
1. Barrier alignment: when the marker arrives on one input, stop reading
   that input until the marker has arrived on all inputs; then snapshot and
   forward one marker.
2. Unaligned: forward the first marker and record the in-flight rows from
   other inputs as part of the checkpoint.

**Recommendation.** Barrier alignment. It needs no change to the marker
format and no in-flight log; the cost is a pause on fast inputs while slow
ones catch up, which is acceptable for the pipeline workloads in question.

**What settles it.** P1 shows a union of two rate sources aligning; your
preference on whether unaligned checkpoints are wanted later.

---

## S5. The state store

**Context.** Windowed aggregates, key-latest and deduplicate hold state that
must survive a restart and be snapshotted at each checkpoint.

**Options.**
1. A directory per run under the pipeline's checkpoint location, with one
   immutable Arrow file per checkpoint per operator (a segment) and a manifest
   that names the segments making up the current state.
2. An embedded key-value store (a new dependency) with its own snapshots.

**Recommendation.** The directory, with one manifest per recorded
checkpoint. Recovery reads the manifest of the checkpoint the run resumes
from, never the newest, because an operator may have written state for a
checkpoint the coordinator never recorded, and pairing that state with older
positions would apply rows twice. Segments are deleted only after a later
checkpoint is recorded. A snapshot is read back only under the column types
it was written with. An operator whose state shrinks, as eviction makes it,
rewrites its state as one compacted segment, since appending segments cannot
express removal; the prototype writes one compacted segment at every
checkpoint, segment first and manifest last, each by rename, so an existing
manifest names complete segments. A replay that reaches a checkpoint id
again rewrites that id's segment and manifest; this is safe only because the
restart point never moves past the recorded checkpoint, which the sink
ordering rule in S6 guarantees. No new dependency; the files are inspectable
with any Arrow tool.

**What settles it.** Your preference; P4 writes and recovers the store.

---

## S6. How a sink commits

**Context.** A sink receives rows between checkpoints and must make them
durable exactly once, including across a restart that replays rows after the
last checkpoint.

**Options.**
1. One transactional write per checkpoint, tagged with the checkpoint id in
   the target's commit metadata; on replay the sink reads the target's last
   tag and skips a checkpoint it already committed.
2. A write-ahead log kept by the sink, applied to the target after the
   checkpoint.

**Recommendation.** The tagged write, with one ordering rule that the
prototype showed to be necessary: a sink commits checkpoint N only after the
coordinator has durably recorded N's positions, and a restart resumes from
the positions of the last checkpoint the sinks hold, which with several
sinks is the least last-committed id among them. Without the rule a sink
that committed N before the positions were recorded would see a restarted
run reissue id N at a different boundary, skip it as already committed, and
lose the rows between the two boundaries. For Delta the tag is Delta's own
idempotent-write pair, `txnAppId` (the query id) and `txnVersion` (the
checkpoint id): the commit carries a transaction action for the pair, and a
write whose version is at or below the one the table records for that app
id is skipped without writing, removing or committing anything, as Delta
Lake defines it; the last committed id is the snapshot's transaction version
for the query id. Iceberg commits carry the tag as metadata. A file table
stages into a directory named by the checkpoint id and renames it at commit,
and a directory already present means already committed. No log to maintain.
For change capture the merge is two commits,
auxiliary table then target, as in Spark; both carry the tag, the checkpoint
counts as committed only when both do, and the reduced rows are sealed before
the first merge so that a retry reads the same winners.

**What settles it.** P2 shows it on a file table and on Delta with a restart.

---

## S7. Watermarks and late rows

**Context.** An event-time window must know when no older rows will come. The
model has a watermark marker emitted by a source; nothing emits or consumes
it today.

**Options.**
1. A watermark operator placed where the user declared it (it may follow
   filters, projections and renames) emits the marker from the rows that
   reach it, as the event time minus the user's delay, never moving back, in
   whole milliseconds. A row is late only when every window it belongs to has
   ended at or before the watermark. An operator with several inputs takes
   the minimum of their watermarks at the point where its inputs merge: the
   merge keeps each input's latest watermark, forwards the minimum over the
   inputs still running once each has sent one and only when that minimum
   advances, ignores a watermark that would move an input back, lets an input
   that has ended stop holding the minimum back, and forwards nothing once
   every input has ended. A downstream operator sees one combined value, and
   that is the value a checkpoint records.
2. The same, plus an allowed-lateness window during which a late row is
   still applied and a correction is emitted as a retraction plus a new row.

**Recommendation.** Option 1 first. Spark applies the watermark of the
previous microbatch to the next; here the marker advances as rows arrive, so
a row arriving with the row that advanced the watermark can be late. That is
a deliberate, observable difference, kept with its tests marked. The
retraction flag makes option 2 natural later.

**What settles it.** P4; your view on whether allowed lateness belongs in the
first version.

---

## S8. Which stateful operators first

**Context.** The pipeline tests ported from Spark exercise windowed
aggregates, deduplication, key-latest (for change capture) and stream-to-stream
inner joins.

**Options.**
1. The first three now, joins later.
2. All four now.

**Recommendation.** The first three. Joins have the largest state and the
least-used semantics in pipelines; leaving them out keeps the first version
reviewable, and the analysis-time refusal names the join as unsupported, as it
does today.

**What settles it.** Your preference.

---

## S9. How a bounded run ends

**Context.** A pipeline run must process what the sources hold at its start
and finish, which is Spark's "available now" semantics.

**Options.**
1. Each source fixes its end position at start and emits end of data on
   reaching it; the sink finishes after the next checkpoint. The coordinator
   issues that final checkpoint when every source has reported end of data.
2. The coordinator stops the sources at a chosen time.

**Recommendation.** Option 1; it is what the end-of-data marker was defined
for (its documentation in `marker.rs` says the sink waits for the next
checkpoint marker and then the job finishes), and a continuous run is the same
plan with no end position. Spark 4.2.1 was checked at the source: the graph
executor uses the available-now trigger for every streaming flow and the
command protocol has no continuous mode.

**What settles it.** P1 and P3 show it.

---

## S10. Apache Iggy as a source

**Context.** Iggy is a message broker with streams, topics and partitions and
monotonic offsets per partition. Spark has no Iggy source, so this is a Sail
addition.

**Options.**
1. An optional crate behind a cargo feature, off by default, holding the
   broker client; positions are offsets per partition; a partition whose
   retained offsets no longer cover the recorded position, or that was
   recreated, fails the run.
2. In the default build.

**Recommendation.** Option 1. One note: the broker client's dependency floor
(reqwest, quinn) is above your lockfile today, so the crate cannot build on
`main` until either a client release fits or the lockfile moves. P3 is built
on our branch for that reason and offered only when the floor fits.

**What settles it.** Your preference on the feature, and on whether a lockfile
move for the client is acceptable when the time comes.

---

## S11. Ordering, ties and deletes in change capture

**Context.** Spark keeps no per-key operator state for change capture: each
microbatch is reduced to one row per key, then merged into an auxiliary table
of tombstones and into the target, whose metadata column holds each row's
last upsert and delete sequences. Which of two rows with equal key and
sequence wins within a microbatch is undefined in Spark.

**Options.**
1. Keep Spark's shape: reduce within one checkpoint interval only, no
   cross-interval state in the operator, deletes carried with their
   sequence, both merges tagged; fix the tie by source position.
2. A key-latest operator that remembers every key and emits retractions.

**Recommendation.** Option 1. Option 2 duplicates the target, grows without
bound and must be recovered; it also cannot express the four tombstone rules,
which need the delete and its sequence. The deterministic tie is a deliberate
difference from Spark and is recorded as such.

**What settles it.** Your preference; P4's companion test for change capture.

---

## S12. Key drift and full refresh

**Context.** Spark records the key columns on the auxiliary table when it is
created and refuses a later run whose keys differ; only a full refresh changes
them. A full refresh replaces the target's schema and keys, empties the
auxiliary table and reprocesses the source from its origin.

**Recommendation.** Keep both. The merge sink reads the stored keys before its
first commit. A full refresh discards positions and operator state, empties
both tables, and asks each source whether it still holds its origin; a source
that does not refuses the refresh rather than rebuild a target missing its
oldest changes.

**What settles it.** Your preference on whether the origin check belongs on
the checkpointable-source interface.

---

## S13. What the lease guarantees, and for which targets

**Context.** Two runs could write one change-capture target. A lease in the
control store exists today for durable change-capture runs on Delta targets
that no catalog manages; targets a catalog manages run without it.

**Options.**
1. Keep it: a commit carries the lease's epoch and the table refuses an
   older epoch; a run that starts after a crash waits out the dead owner's
   lease and takes over.
2. A lock that makes the second run fail at start.

**Recommendation.** Option 1, as today. The fence is what protects the target;
a lock would not stop an owner paused past its lease from writing after a
successor started.

**What settles it.** Your preference, and whether catalog-managed targets
should gain a fence later.
