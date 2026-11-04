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
records the positions. Something must: the coordinator.

**Options.**
1. In the session, next to the streaming-query manager that already tracks
   query ids, status and stop requests.
2. In the execution driver, which already owns job state, task placement and
   worker lifecycle, in both local and cluster mode.

**Recommendation.** The driver. In cluster mode the sources run on workers and
the driver is the one place that can ask all of them to mark and can collect
their positions; local mode runs a driver too, so one implementation serves
both. The session keeps what it has: the query handle, status, stop.

**What settles it.** Your preference, and the prototype P1, which puts a
coordinator in the driver and shows a bounded query over two rate sources
checkpointing and finishing.

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

**Recommendation.** The directory. Recovery is a manifest read followed by
segment loads; no new dependency; the files are inspectable with any Arrow
tool; segments older than the last checkpoint are deleted by the manifest
writer. Compaction, when state grows, is a merge of segments into one, also
written as a new segment.

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

**Recommendation.** The tagged write. Delta and Iceberg commits carry
metadata; a file table stages into a directory named by the checkpoint id
and renames it at commit, and a directory already present means already
committed. No log to maintain.

**What settles it.** P2 shows it on a file table and on Delta with a restart.

---

## S7. Watermarks and late rows

**Context.** An event-time window must know when no older rows will come. The
model has a watermark marker emitted by a source; nothing emits or consumes
it today.

**Options.**
1. The source emits watermarks from the event-time column the user
   declares, minus the user's delay; an operator drops a row whose event
   time is below the watermark it has seen, and counts it.
2. The same, plus an allowed-lateness window during which a late row is
   still applied and a correction is emitted as a retraction plus a new row.

**Recommendation.** Option 1 first. The retraction flag makes option 2
natural later, since a corrected window result is exactly a retraction of the
old result and an emission of the new one.

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
