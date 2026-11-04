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

 execution (sail-execution driver)
   jobs, tasks, workers                        exists
   checkpoint coordinator                      new: ids, requests, positions,
                                               final checkpoint at end of data

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
   on every source. Each source emits the marker after its current rows.
2. Each operator snapshots its state when the marker has arrived on all its
   inputs (barrier alignment), then forwards the marker.
3. The sink commits its buffered rows tagged with the id and acknowledges.
4. The coordinator asks each source for its position at the id and records
   the set as the run's last checkpoint.

A bounded run differs only at the start (`bound_now()` on every source) and
at the end (the final checkpoint once every source reported end of data; the
sink finishes after committing it).

## Data flow for change capture

```
 change rows ──▶ key-latest ──▶ merge sink ──▶ target
                 (emits retraction of the previous row for a key,
                  then the new row; keeps latest per key by sequence)
```

The merge sink turns retractions into deletes by key and data rows into
inserts, applied as one transaction at the checkpoint. A target without
transactions is written by replacing the affected partitions. A lease in the
existing control store stops a second run from committing to the same target.

## Recovery

On start, the pipeline layer reads the run's last recorded checkpoint. Each
source is given its position; each stateful operator loads the live segments
named by the manifest; each sink reads the target's last commit tag. Rows
replayed between the recorded positions and the sinks' last tags are
re-applied by operators (their state was snapshotted before those rows) and
skipped by sinks whose tag already covers them. There is no reconciliation
step: the checkpoint is the only unit of durability.

## Failure cases, by component

| Failure | What happens |
| --- | --- |
| A source cannot reach its recorded position (retention gap, recreated partition) | The run fails at start with the partition named; nothing is written. |
| A worker dies mid-checkpoint | The checkpoint is abandoned; the run restarts from the previous one. |
| A sink commit fails after the target applied it | The next start reads the target's tag, sees the id, skips the replay. |
| A sink commit fails before the target applied it | The replay commits it. |
| State segment missing | The run fails at start with the operator and id named; no partial state is used. |
| Two runs on one change-capture target | The second cannot take the lease and fails before writing. |

## What is deliberately simple

One coordinator per run, in-memory until the final design decides durability
of positions (the prototype keeps them in memory; the real design writes them
beside the state manifest). One alignment scheme. One state format. Each can
be replaced behind its interface without touching the others.
