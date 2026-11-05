# Streaming pipelines and change capture on Sail

Streaming pipelines maintain tables as new source data arrives, without
rebuilding them from their entire history. Change capture applies keyed
updates and deletes in sequence order, even when older changes arrive late.
The proposal is to provide both through Sail's existing flow-event execution
model, with checkpoints that make interrupted writes recoverable.

Start with one flow, a declared computation feeding a target. Include change
capture if recovery across its two table writes is accepted; otherwise begin
with append-only output. Coordinate independent flows and add broader
stateful operators only when their use cases justify the extra machinery.

## Fit with Sail

Sail already represents a stream as ordered flow events: data batches,
retractions that cancel previous rows, and control markers. This supplies the
execution model. The missing pieces are agreements about recoverable source
positions, saved state, output commits and run completion.

| Existing Sail foundation | Proposed addition | Architectural consequence |
| --- | --- | --- |
| `StreamSource` supplies a streaming scan | Optional capability for checkpoint requests, resumable positions and bounded ends | Sources without that capability remain usable where recovery is not required |
| Data and markers travel through the same streaming plan | Align checkpoint markers across participating inputs | Preserve the event model; define a consistent boundary through the computation |
| Local execution uses a job runner; cluster execution has a driver and worker tasks | Use job-runner coordination when the recovery domain fits one job; delegate through the driver in cluster mode | Avoid adding a driver to local execution; reach distributed sources through their running tasks |
| The streaming rewriter supports sources and stateless operations | Admit append sinks and a change-row reducer with a merge sink | Extend supported plans explicitly; do not imply support for windows, joins or arbitrary aggregates |
| End-of-data is followed by a checkpoint | Report bounded success only after the final checkpoint's required writes complete | Reaching a source end is distinct from making its output durable |

A checkpoint names the input boundary, any operator state at that boundary,
and the output work associated with it. The existing
[marker contract](https://github.com/lakehq/sail/blob/62251e0a27bbab0a15547562e829cad2a418f353/crates/sail-common-datafusion/src/streaming/event/marker.rs)
provides the ordering foundation. The additions above define persistence and
recovery around that ordering; they do not introduce a second streaming engine.

## Why the initial scope matters

A recovery domain is the set of writes tracked together so a restart can
finish incomplete work. One append flow can commit to one transactional
table. One change-capture flow writes both its target and an auxiliary table.
That table retains deletion sequences so an older update cannot resurrect
a deleted key. Consequently, one flow does not always mean one transaction.

For an append example, suppose a checkpoint covers three rows and uses the
same commit identifier at two tables. Table A commits; the process fails
before table B commits. Reusing that identifier for the original rows plus
later arrivals makes A skip the later rows as an already completed write.
Giving the entire replay a fresh identifier duplicates the original rows in
A. Recovery must preserve what each committed identifier means. Change
capture uses different merge rules, but its separately committed effects
also need a defined recovery protocol.

| Initial scope | Benefit | Obligation and cost |
| --- | --- | --- |
| One append transaction | Smallest complete source-to-table path | Recover the source boundary and table commit consistently; defer change capture |
| One flow including change capture | Supports keyed updates and deletes | Preserve repeatable retry input and track the auxiliary and target writes separately |
| Several independent flows or sinks | Recover several outputs as one unit | Coordinate participation, ownership and completion across their failures |

**Recommendation:** support one flow, including change capture with the
protocol below. This addresses the required table behavior without adding
coordination across independent flows. Append-only is a useful smaller
alternative if the two-write protocol should be deferred. Neither choice
permits loss or duplication within its promised scope.

Recovery here means completing required writes correctly after a crash.
It does not promise atomic visibility across tables; readers may observe
partial progress before recovery finishes.

## A candidate execution and recovery protocol

The source reports positions with enough identity to distinguish the same
source from a replacement. A position also needs a defined replay guarantee;
an offset alone does not promise that the same rows remain available.

At a checkpoint, an operator with several inputs holds each input at its
marker until the others reach the same marker. This barrier alignment avoids
having to save rows still travelling between operators, but waits for slower
inputs. Serializing checkpoint requests is the simplest initial way to keep
an ordinary checkpoint and a final checkpoint from replacing one another.

Before writing output, persist a prepared record binding the checkpoint to
its source boundaries, relevant state and table effects. Persist output rows
when re-evaluation cannot be shown to reproduce the same result. For change
capture, seal the chosen rows: save them unchanged for every retry. Each
table effect has its own completion record. On restart, finish the original
pending effects before advancing to a new boundary.

This is a proposed contract, not a requirement for a new storage subsystem.
Reuse existing publication, archive and write-completion mechanisms where
they fit. An alternative replay design is reasonable if it proves that the
same inputs and transformed output remain available until all effects finish.

Delta's application identifier and transaction version are candidates for
identifying repeated append writes. They do not by themselves implement
change-capture merge recovery, refresh identity or writer ownership.
Those guarantees must be established for each admitted target.

## Change-capture behavior to preserve

Each change row has a key, a sequence value and an action: an upsert inserts
or updates that key, while a delete removes it.
Validate every original row before reducing an interval to one winner per
key. Otherwise an invalid row can disappear because a later valid row wins.
Retain deletes with their sequence values; a deletion is not a retraction
of some previously emitted row.

The proposed ordering rules follow Spark 4.2.1: an upsert can replace a live
row at an equal or greater sequence; a delete removes it only at a greater
sequence. The auxiliary table rejects changes older than a stored deletion.
An upsert at or above that deletion sequence clears it. These comparisons
keep cross-interval ordering in the tables rather than an unbounded operator
map of every target key.

Spark leaves equal-key, equal-sequence winners within an input batch
undefined. Keep that freedom when choosing a winner, then seal it so retries
cannot choose differently. A stable winner across independently scheduled
sources would require an additional ordering contract. Spark's
[change processor](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L220)
provides the reference comparisons, not a complete Sail recovery protocol.

A full refresh rebuilds a target and must establish a new recovery identity.
It needs a source-history policy before destructive reset. A writer replaced
by a new owner must not later resume and overwrite newer work; preserve
existing target-enforced fences where supported and define ownership
requirements for other targets. A fence is a target's rejection of writes
from an older ownership number. Ordering table commits alone is insufficient.

## Bounded runs, resources and later operators

For a bounded run, each source captures an end position and reads to it.
These bounds need not describe one simultaneous snapshot across sources.
Spark 4.2.1 available-now execution can process captured ends in several
batches; it does not require one checkpoint for the whole run. Use intermediate
checkpoints plus a final checkpoint, and finish only after the required writes.
A continuous run uses the same checkpoint protocol without a captured end.

Checkpoint frequency trades replay size against commit and snapshot work.
It does not bound memory. Buffered output needs byte limits, backpressure or
spill; retained state needs a size policy and safe reclamation. State required
by an incomplete write or valid restart point cannot be deleted merely
because a newer source position was recorded.

Windows and duplicate removal need additional state and event-time rules.
Sail's watermark marker promises that older timestamped rows will not follow.
A threshold derived from observed timestamps does not guarantee that promise
when late data can arrive. Before adding windows, either enforce the promise before rows enter the
downstream stream, including arrivals after a watermark, or explicitly
change the marker contract.
This choice need not block a stateless append path or interval change reduction.

Apache Iggy, a partitioned message broker, is an optional source candidate.
Its position must include the partition incarnation, which distinguishes
recreation from continuation, and reads must detect missing retained data.
Its client dependencies are a separate admission question; another source
can demonstrate the core protocol first.

## Decisions and decisive evidence

The initial scope comes first because it determines which writes must recover
together. That determines viable coordination ownership and source contracts.
State and resource choices then follow the selected operators. These questions
can feed back into one another; they are not a mandatory sequence of isolated
approvals.

Three decisions would make the next implementation concrete:

1. Include change capture in the first flow, or establish append-only recovery
   first? The recommendation is change capture with separate effect completion.
2. Does job-runner coordination with an optional source capability fit Sail's
   execution ownership, and is the prepared-record protocol the right way to
   preserve partial work? Prefer reuse where an existing mechanism fits.
3. Which source and target pair should demonstrate the contract first, and
   what replay, refresh and writer-ownership guarantees can that pair provide?

Mechanism tests cover marker alignment, a simulated single-file-sink restart,
separate Delta write options and state restored from recorded events. They do
not establish the integrated durable protocol. The decisive test must restart
around each table commit, preserve validated retry rows, exercise overlapping
checkpoint requests and staggered source completion, and reject incompatible
source identity or stale writers. Add source-to-table Spark comparisons for
the selected behavior. Broader operators should follow only when their own
state and recovery contracts are defined.
