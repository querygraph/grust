# Streaming tables and change capture: architecture overview

The component view behind STREAMING-ON-STREAMSOURCE.md, for review. Terms as
in DECISION-NOTES-STREAMING.md.

## Components and who owns what

```
 pipeline layer (sail-spark-connect/pipelines)
   registration, analysis, scheduling          unchanged
   incremental dataset -> streaming plan       new: builds through the rewriter
   run = streaming query under the session's   new: start, wait or leave running
         streaming-query manager

 planning (sail-plan streaming rewriter)
   table scans of stream sources -> scans      exists
   batch inputs -> adapter + end of data       exists
   projection, filter, limit, union            exists
   windowed aggregate, key-latest, dedup       new logical and physical nodes
   append sink, merge sink                     new sink nodes

 execution (sail-session job runners, sail-execution driver)
   local runner (no driver), cluster runner    exist
   checkpoint coordinator, per query, owned    new: ids, requests, positions,
   by the job runner: in process locally,      final checkpoint at end of data;
   delegated to the driver in cluster mode     cluster mode reaches a source
                                               through the task that runs it

 sources (sail-data-source, sail-iggy)
   stream-source trait                         exists
   checkpointable-source interface             new, implemented by Iggy;
                                               rate gains it for tests only

 state (new, small crate or module)
   per-run directory of segments + manifest    new

 sinks (sail-data-source, lakehouse crates)
   checkpointed append (file, Delta, Iceberg)  new
   checkpointed merge (Delta, Iceberg, Hive)   new
```

## Data flow for one streaming table

```
 source ──data──▶ filter ──▶ window aggregate ──▶ append sink ──▶ table
   │ markers:  checkpoint(id), watermark, end-of-data pass through
   │                                                      │
   └──────── positions ◀── coordinator ──▶ commit(id) ────┘
```

1. The coordinator decides a checkpoint and calls `request_checkpoint(id)`
   on every source: directly in local mode, through the task that runs the
   source's partition in cluster mode, since the scan is rebuilt on the worker.
   Each source emits the marker after its current rows.
2. Each operator snapshots its state when the marker has arrived on all its
   inputs (barrier alignment), then forwards the marker.
3. The coordinator asks each source for its position at the id and records
   the set durably as checkpoint N.
4. Only then does each sink commit its buffered rows tagged with the id and
   acknowledge. The order matters: a commit before the positions are
   recorded would let a restart reissue the id at another boundary and lose
   rows.

A bounded run differs only at the start (`bound_now()` on every source) and
at the end (the final checkpoint once every source reported end of data; the
sink finishes after committing it).

## Data flow for change capture

```
 change rows ──▶ interval-reduce ──▶ merge sink ──▶ auxiliary table (tombstones)
                 (one row per key per      │
                  checkpoint interval,     └──────▶ target (metadata column)
                  deletes with sequence)
```

The operator holds nothing across intervals; ordering lives in the target's
metadata column and the auxiliary table, as in Spark. At the marker the sink
seals the reduced rows, merges them into the auxiliary table, then into the
target, tagging both commits with the checkpoint id. A target without
row-level operations is refused. On a Delta target that no catalog manages, a
lease in the existing control store fences commits by epoch; a successor
waits out a dead owner's lease and takes over.

## Recovery

On start, the pipeline layer reads the sinks' last committed ids and
resumes from the least of them, N; the coordinator's record of N's positions
exists, because positions are recorded before any sink commits. Each source
is given its position at N; each stateful operator loads the manifest of
that recorded checkpoint, never the newest one; each sink reads the target's
last commit tag. Rows replayed between the recorded positions and the sinks'
last tags are re-applied by operators and skipped by sinks whose tag already
covers them. Change capture does not rely on the re-read being identical: the
sealed rows of each checkpoint are archived before the merges and restored on
recovery. A streaming table whose re-read is not guaranteed identical is
refused at analysis. There is no reconciliation step: the checkpoint is the
only unit of durability.

## Failure cases, by component

| Failure | What happens |
| --- | --- |
| A source cannot reach its recorded position (retention gap, recreated partition) | The run fails at start with the partition named; nothing is written. |
| A worker dies mid-checkpoint | The checkpoint is abandoned; the run restarts from the previous one. |
| A sink commits N, then the run dies | The restart resumes from N's recorded positions; the table holds N; nothing is replayed twice or lost. |
| N's positions are recorded, then the run dies before the sink commits N | The restart resumes from N minus 1, reuses id N at its own boundary, and the table, which does not hold N, commits it; every row once. |
| State segment missing | The run fails at start with the operator and id named; no partial state is used. |
| Two runs on one unmanaged Delta change-capture target | The second waits out the first's lease if the first is dead and takes over; a commit from the older epoch is refused by the table. |
| A crash between the auxiliary-table merge and the target merge | The checkpoint is not committed; the sealed rows are restored and both merges rerun; the auxiliary merge is idempotent by tag. |
| An operator wrote state for a checkpoint never recorded | Recovery reads the recorded checkpoint's manifest, so that state is ignored. |

## What is deliberately simple

One coordinator per run, in-memory until the final design decides durability
of positions (the prototype keeps them in memory; the real design writes them
beside the state manifest). One alignment scheme. One state format. Each can
be replaced behind its interface without touching the others.

## What is reused from the current implementation

Read from the current code by the person who built the change-capture
runtime; line counts are of the files as they stand.

| Carries over | Why |
| --- | --- |
| The flow binder and admission (which query shapes a streaming flow may contain, how its reads bind), about 1,450 lines | Works on the plan before any source model |
| The watermark rule and the late-row rule, about 350 lines | Spark's rule; the value comes from the watermark marker instead of from the rows |
| The stateful operators for deduplication, deduplication within the watermark, and join eviction, about 1,370 lines | Driven by a watermark value, whichever carries it; re-keyed by checkpoint id |
| The change-capture definitions, name folding and their oracle, about 5,000 lines | Parse Spark's statements; no source model |
| The merge paths for the four target kinds, about 1,100 lines | A lakehouse commit is bounded by nature; the unit becomes the checkpoint |
| The control model's lease, fence, guard and reset rules, most of 4,200 lines | Keyed by a sequence number; the checkpoint id is that sequence |
| The ported Spark 4.2.1 suites, 75 files | Assert table contents after a run; unchanged |

| Replaced, not adapted | Why |
| --- | --- |
| The bounded-source contract, the Iggy bounded source, the Delta bounded reads | Positions, ranges, retention and incarnations become the checkpointable-source interface and offsets per checkpoint |
| The per-batch intent and progress digests | The interval between two checkpoint markers replaces the batch |
| The range plumbing in the append path and the batch half of the change-capture source | Plans one bounded scan per source per batch |
| The batch loop of the change-capture run, its archive and replay by intent | Replay becomes resume from checkpoint positions |

