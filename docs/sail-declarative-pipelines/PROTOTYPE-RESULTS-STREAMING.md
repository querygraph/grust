# What the streaming prototypes showed

Four prototypes test the redesign of streaming on Sail's flow event model.
A flow event is a batch of rows or a marker, a control signal that travels
in order with the rows. Each prototype answers one question from the
decision notes. All four are local builds, not pull requests.

## P1: checkpoints as markers

**Question.** A checkpoint is a consistent cut of a running query, so that
a restart loses and repeats nothing. Can it travel as a marker through the
existing plan, with no microbatch loop?

**What it showed.** A coordinator gives each checkpoint an id, asks every
source to emit a marker with it, and records each source's position. A
position is where the source would resume. A new merge operator joins
partitions into one stream and forwards a checkpoint marker once every
input has sent it. A bounded query finishes when its sink sees the
end-of-data marker followed by a checkpoint. The merge also forwards the
least watermark of the inputs still running. A watermark is a marker
saying no older row will follow.

| Test                                                 | Runs passed |
| ---------------------------------------------------- | ----------- |
| Two sources, unioned, filtered, merged and collected | 20 of 20    |
| Marker order out of a four-partition merge           | 20 of 20    |
| Watermark combination over three inputs              | 20 of 20    |

**What it changed.** Local mode has no driver, so the coordinator belongs
to the component that runs the query.

**What it leaves out.** Cluster mode and a durable coordinator record.

## P2: one table commit per checkpoint

**Question.** Can a sink commit exactly once per checkpoint?

**What it showed.** Tagging each commit with its checkpoint id and
skipping ids the table holds is not enough. If the sink commits checkpoint
N and the query dies before N's positions are recorded, the restart
resumes from the checkpoint before N. It then reaches a new boundary also
numbered N, skips it, and loses the rows between the two boundaries. The
fix has two parts. A sink commits N only after N's positions are recorded.
A restart resumes from the last checkpoint the table holds, and with
several sinks, from the least of those.

For Delta tables the tag is Delta's idempotent write, the txnAppId and
txnVersion options, which Sail declared but did not support. A write whose
version is at or below the one recorded for its application id is skipped
in every save mode, committing nothing.

| Test                                           | Passed   |
| ---------------------------------------------- | -------- |
| Death after a commit, restart: every row once  | 20 of 20 |
| Death before a commit, restart: every row once | 20 of 20 |
| Idempotent write cases on Sail                 | 9 of 9   |
| The same cases on Spark 4.2.1 with Delta 4.4.1 | 9 of 9   |

**What it changed.** The decision on how a sink commits states the
ordering rule and covers both crash windows. The idempotent write is a
candidate for a small pull request on its own.

**What it leaves out.** Retractions and other table formats.

## P3: Apache Iggy as a stream source

**Question.** Apache Iggy is a message broker. A poll past retained data
silently skips ahead, and a recreated partition reuses its id with offsets
restarting at zero. Can the existing bounded Iggy adapter become a
checkpointed stream source and still fail closed on both?

**What it showed.** Every page is read through the adapter's exact-range
reader, so every reply is checked for the offset asked for and for the
partition's incarnation, the broker's count of recreations. A position is
the next offset and incarnation of each partition.

| Test against the pinned broker                           | Passed   |
| -------------------------------------------------------- | -------- |
| A bounded run reads each message once                    | yes      |
| A resume reads each new message once                     | yes      |
| A resume below retained data fails, naming the partition | yes      |
| A resume onto a recreated partition fails, naming it     | yes      |
| All four, repeated on idle cores                         | 20 of 20 |
| All four, repeated with every core saturated             | 15 of 15 |

In one run, retention overtook a resume and the gap appeared mid-run. The
check caught it there, which is why it runs on every poll. A query can
also end before the coordinator records the final checkpoint.

**What it changed.** A bounded run is finished when the coordinator says
so, not when the query's stream ends.

**What it leaves out.** Wiring into the pipelines' Iggy format, and
upstream's lockfile, which is below the client's dependency floor.

## P4: windowed state in files

**Question.** Can a stateful operator keep state across checkpoints in
plain files and recover it exactly?

**What it showed.** A tumbling window aggregate counts and sums per window
and key. A row whose window ended at or before the watermark is dropped
and counted as late. A watermark closes the windows it passed and emits
their results. At each checkpoint the operator writes its open windows,
watermark and late count as one Arrow file, a segment, plus a manifest
naming it, each by rename, manifest last. A restart reads the recorded
checkpoint's manifest and refuses a segment under other column types. A
companion function reduces one interval of change rows to the latest per
key, giving ties to the later row and keeping deletes with their sequence
value.

| Test                                                    | Runs passed |
| ------------------------------------------------------- | ----------- |
| Windows and late count over a recorded input            | 20 of 20    |
| Restart reproduces the remaining output and final state | 20 of 20    |
| A snapshot under another key type is refused            | 20 of 20    |
| Interval reduce with a tie and a delete                 | 20 of 20    |

Disabling the restore fails the restart and refusal tests.

**What it changed.** The decision on the state store states the rename
order, and that rewriting a replayed checkpoint is safe only because a
restart never passes the recorded checkpoint.

**What it leaves out.** The watermark operator, sliding windows, allowed
lateness, joins and removal of old segments.

## What the four establish

The flow event model carries the whole exactly-once path without a
microbatch loop. Sources emit markers on request, a merge aligns them,
sinks commit once per checkpoint under an ordering rule, and stateful
operators recover from files. Each piece fails closed where data would
otherwise be lost or repeated.

They do not establish cluster execution, a durable coordinator, speed, or
the planner changes that would place these operators in a user's query.
Change capture has its reduction and its tagged Delta write, but not the
two merges per interval that Spark performs.
