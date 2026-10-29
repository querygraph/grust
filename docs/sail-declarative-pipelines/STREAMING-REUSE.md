# Streaming reuse from Sail-Iggy

This is a source review for the streaming phase after batch acceptance. It does
not claim that the integration was built or its broker tests rerun here.

## Reviewed sources

| Source | Revision and scope |
| --- | --- |
| Private `lakehq/sail-iggy` | `codex/iggy`, `5816b9b2f3bd20cd124f24128b7e45818351bcc1`. The default `main` branch at `43687e649d53770fb74ff7bd1ddc4160032e064e` does not contain the integration. |
| Local Apache Iggy, `/Users/alexy/src/iggy` | `153fdf466aea94b7bcb90681ee7274f9f76ec00d`, read using pinned Git objects. The checkout is active independently, so its current HEAD is not a stable review reference. |
| Sail SDP base | `0ba425c0331aee4dd4e9a280c6a793926fd0876e`; the implementation branch uses DataFusion 55.2.0. |

The private branch uses DataFusion 54.0.0 and Iggy `0.10.1-edge.2`. The inspected
local Iggy SDK declares `0.11.1-edge.5`. Reuse requires a deliberate API port and
fresh tests; copying the branch or assuming that its SDK behavior is current is
not sufficient.

## What is reusable

The feature-gated table format in
[`sail-data-source/src/formats/iggy`](https://github.com/lakehq/sail-iggy/tree/5816b9b2f3bd20cd124f24128b7e45818351bcc1/crates/sail-data-source/src/formats/iggy)
fits Sail's existing `TableFormat`, `StreamSource`, flow-event, and extension
planner interfaces. It supports append-only reads and writes, JSON/raw payloads,
partition routing, and a raw archival envelope. Registration is conditional in
`sail-session`'s format registry and physical planner. Preserve this optional
dependency boundary when porting the connector.

The separate
[`sail-iggy-mirror` coordinator](https://github.com/lakehq/sail-iggy/blob/5816b9b2f3bd20cd124f24128b7e45818351bcc1/crates/sail-iggy-mirror/src/coordinator.rs)
is the more useful starting point for durability. Its `MirrorSource` and
`MirrorSink` interfaces separate polling from committing and acknowledging:

1. Load the sink's committed cursor and derive the next explicit source offset.
2. Poll a bounded batch with broker auto-commit disabled.
3. Check partition identity, contiguous offsets, retention gaps, and overflow.
4. Commit rows and the application transaction version together in Delta.
5. If the commit response is ambiguous, reload the durable cursor before
   deciding whether to retry or acknowledge.
6. Acknowledge Iggy only after the sink commit is confirmed. A failed broker
   acknowledgment does not erase the durable commit or control restart.

Its tests cover failure before commit, response loss after commit, restart,
missing cursors, idempotent initialization, acknowledgment failure, broker
integration, and restoring the Delta log/data plus archived schema descriptor.
These are useful scenarios to port. Their presence is source evidence, not a
passing-test verdict for current Sail or Iggy.

The Delta adapter uses `txn_app_id` and `txn_version` in the writer and validates
the stored transaction afterward. It forbids expiring the authoritative cursor.
The current Sail base does not expose those writer options; adding the necessary
transaction action and serialization is a separate, reviewable prerequisite.
Use Sail's normal planner and `JobService` when integrating this into SDP. The
mirror's private `SessionContext` and `MirrorQueryPlanner` are specific to its
standalone worker and should not become a second execution path inside Sail.

## Gaps to address before SDP reuse

| Observed boundary | Required streaming work |
| --- | --- |
| `reader.rs` stores `message_offset + 1` before yielding a row when `auto_commit` is enabled. Its restart logic then uses that value as an explicit starting offset. | Disable this path for durable pipelines. Couple progress to confirmed sink commits; do not treat receipt or a yielded batch as durability. A cancellation between storing the offset and committing the sink can otherwise lose data. |
| `writer.rs` flushes on checkpoint markers but records no durable checkpoint identity or recovery result. | Define and test sink commit capabilities and replay behavior. A flush alone is not a transactional streaming checkpoint. |
| The mirror uses one authoritative Delta cursor per source partition and documents one active writer. It has no lease/fencing protocol. | Add fenced ownership and atomic progress updates; prove takeover and stale-writer rejection. The coordinator's acceptance of a newer cursor depends on its single-writer assumptions. |
| `MirrorSource::poll` bounds message count and waiting time, but does not capture a fixed available-data frontier for an entire run. | Snapshot per-partition end positions for bounded SDP runs and keep them stable across retries. |
| Mirror identity is based on source/stream/topic/partition, with one raw envelope per source record. | Introduce stable pipeline/flow/reset identity, multiple source ranges, definition compatibility, and result identities independent of output row counts. This is needed for filters, aggregates, joins, and CDC. |
| Iggy physical source/sink nodes have no encode/decode arms in the branch's `sail-execution/src/codec.rs`. | Add distributed serialization and round-trip tests before claiming worker execution support. |
| The sink strips an unbounded round-robin `RepartitionExec` as a local workaround. | Reproduce and fix the scheduling issue at Sail's shared streaming/planner boundary, preserving partitioning requirements and testing backpressure/cancellation. |

The current Iggy source additionally supplies `ReceivedMessage::position` and
`store_position`, which retain the partition incarnation and ownership context.
Its broker's `Next` strategy starts at the stored **last consumed** offset plus
one. Preserve that distinction from an SDP **next offset**. Use captured
positions when acknowledging asynchronous work, and handle `OperationUncertain`,
`LaneBlocked`, and history/ownership rejection according to the pinned SDK
contract. These APIs are not a replacement for sink fencing or a distributed
transaction between Iggy and a table writer.

## Incremental implementation boundaries

1. Add a small source-independent model for committed input ranges, attempt
   identity, reset generation, and commit outcome. Keep Arrow, Iggy, registry,
   and catalog providers out of the model. Adapt the mirror to import it once
   the common behavior is established; do not import the whole mirror crate.
2. Extract only the required conditional state/replay primitives from LakeCat,
   with LakeCat reimporting the extracted module. Retain `CatalogStore`,
   `CatalogGraphSink`, and `LineageSink` boundaries. Keep pipeline control state
   outside Iceberg metadata and avoid a reverse dependency on `lakecat-sail`.
3. Add source capabilities for repeatable bounded ranges and post-commit
   acknowledgment beside Sail's existing streaming interfaces. Implement the
   Iggy adapter with explicit offsets and captured source positions.
4. Add transactional sink commit/recovery through existing Sail writers, first
   for a supported lakehouse target. Port the mirror's ambiguous-outcome and
   restore cases, then add fencing and concurrent-owner cases.
5. Integrate the state machine with pipeline lifecycle and `JobService`, using
   Sail's actor/service conventions. Test selective refresh, full refresh,
   cancellation, source growth, session restart, and worker failures.
6. Port the optional Iggy output adapter with explicit delivery capabilities,
   distributed codecs, and broker-backed tests. Do not infer exactly-once
   output from deterministic message IDs without verifying broker deduplication
   scope, retention, and recovery semantics.
7. Only after streaming acceptance, implement Spark 4.2.1 CDC on this durable
   commit contract.

Grust's already extracted topology kernel remains the graph dependency. There
is no reason to bring graph stores or the Grust Sail adapter into the streaming
runtime. The reusable pieces are small control and recovery modules, with the
Iggy and lakehouse implementations remaining optional adapters.
