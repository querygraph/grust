# CDC activation: running SCD1 flows in a triggered pipeline run

Design checkpoint, user-notified (2026-10-31). Units A1–A4c deliver every
piece of the SCD1 write path as components with Spark-ported tests; nothing
runs them from a pipeline run. This document pins what Spark does per run
and proposes the smallest activation that keeps the Astra durability
decisions open, so the user can decide the three points at the end.

## Spark 4.2.1 per run (pin `617618396`)

- `PipelineExecution.startPipeline` (`PipelineExecution.scala:45–60`):
  resolve and validate the graph, `State.reset(resolvedGraph, context)`
  (`:50`) rolls the streaming checkpoint directory of every flow selected
  for full refresh (`State.scala:72–100`), then
  `DatasetManager.materializeDatasets` (`:53`, the A1 contract), then the
  graph execution starts.
- `TriggeredGraphExecution` (`TriggeredGraphExecution.scala:40–140`): every
  streaming flow runs with `Trigger.AvailableNow()` (`:77`); flows are
  queued and started in topological order on an execution thread, bounded
  by `maxConcurrentFlows`, with watchdog retries between
  `watchdogMinRetryTimeInSeconds` and `watchdogMaxRetryTimeInSeconds`; a
  flow's terminal failure fails the run.
- `FlowPlanner.plan` (`FlowPlanner.scala:41–95`): an `AutoCdcMergeFlow`
  becomes `Scd1MergeStreamingWrite` with `trigger = triggerFor(flow)` and
  `checkpointPath = flowMetadata.latestCheckpointLocation`.
- `SystemMetadata` (`SystemMetadata.scala:40–80`): the checkpoint root is
  `<storageRoot>/_checkpoints/<destination table>/<flow>`, and the latest
  checkpoint is the highest numbered subdirectory; a reset creates the next
  number (`State.scala:81–100`).
- `Scd1MergeStreamingWrite.startStream` (`FlowExecution.scala:640–660`):
  `createAuxiliaryTableIfNotExists` once at flow start (A4c
  `ensure_auxiliary_table`), then `writeStream.foreachBatch` calls
  `Scd1ForeachBatchHandler.execute(batch, batchId)` per microbatch (A4c
  `handle_microbatch`), with the checkpoint recording the source offsets
  per completed batch. The retry argument (`Scd1ForeachBatchHandler.scala:55–60`)
  makes a replayed batch safe: the auxiliary merge is a no-op against
  state it already advanced, and the target merge's `>=` upsert and `>`
  delete conditions are idempotent.

## Sail today

- Components: the A2 validators, A4a reconciliation, A4b merges and A4c
  handler; the streaming substrate integrated from the earlier units
  (`pipelines/streaming`): `BoundedSource` (immutable incarnations, opaque
  cursors, `plan_end`, `scan` of an explicit range,
  `sail-common-datafusion/src/streaming/bounded.rs:237–270`),
  `RunFrontier::capture`, `Progress::advance`, `next_intent`
  (`streaming/intent.rs`), `binding::validate_reads` and
  `admission::admit` (the stateless subset), and `lower::lower` producing a
  bounded `LogicalPlan` for one intent, plus the in-process
  `DeterministicSource` for tests.
- Missing: a run record (checkpoint) that persists the captured frontier
  and the progress after each batch; a loop that drives intents through
  the handler; the `execution::execute` gate, which still rejects any
  graph with a `Table` or `Sink` output before materialization.

## Proposed minimal activation (unit A5)

`pipelines/autocdc/run.rs`, invoked by `execution::execute` for the AutoCDC
flows of a graph whose streaming outputs are all AutoCDC targets with
bounded sources (every other streaming graph keeps today's rejection):

1. After `materialize::tables` (which already performs the full-refresh
   truncate and auxiliary drop), for each AutoCDC flow in topological
   order: resolve the flow's source binding (`validate_reads`), and read
   or create the run record at
   `<warehouse>/_checkpoints/<destination>/<flow>/<n>` (`n` from the
   highest existing directory; a full refresh of the destination creates
   `n+1`, which is `State.reset`).
2. `ensure_auxiliary_table` once (merge support, key drift, creation).
3. Capture the frontier once per run (`RunFrontier::capture`), then loop:
   `next_intent` → `lower` to the batch plan → `handle_microbatch` with the
   intent index as `batchId` → `Progress::advance` and write the record.
   `Trigger.AvailableNow` semantics: the loop ends when the captured
   frontier is reached; nothing past the frontier is read in this run.
4. Failures: a failed batch leaves the record at the last completed
   intent; the next run replays that intent, which the merge conditions
   make idempotent (Spark's own argument). No watchdog retries in A5: one
   attempt per flow, failure reported as the flow's failure event through
   the existing failure model.

Tests: the full-refresh suite's second-run cases, the durability suite's
cross-run cases through a real run (not handler calls), and a replay case
that fails between the two merges and re-runs.

## Decisions for the user

1. **Run record authority.** A5 writes a local JSON record next to the
   warehouse, single writer, no fencing. The parallel handoff's Astra
   section requires one atomic authority for ownership and progress before
   production effects; A5 is explicitly a local, single-process triggered
   run. Accept that boundary for now, or hold activation until the Astra
   control-store design exists.
2. **Activation gate.** Allow `execution::execute` to run graphs whose
   only streaming outputs are AutoCDC targets with bounded sources, keeping
   the rejection for everything else, or keep the handler test-only until
   general streaming runs exist.
3. **Checkpoint layout parity.** Mirror Spark's `_checkpoints/<dest>/<flow>/<n>`
   under the warehouse (`storageRoot` has no Sail equivalent yet), or
   define a Sail-owned location now.

Default if no answer: 1 accept the local boundary and say so in every
record; 2 allow; 3 mirror Spark under the warehouse.
