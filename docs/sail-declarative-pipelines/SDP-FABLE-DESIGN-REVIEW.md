# SDP design and implementation review for Fable

Please review the complete Sail Declarative Pipelines work, with particular
attention to the proposed streaming/Iggy and CDC architecture. Identify correctness
risks, missing contracts, unnecessary machinery, weak evidence and a realistic
implementation sequence. Distinguish observations from recommendations and open
questions. This document is a review brief, not approval of the unfinished designs.

## Snapshot and objective

- Objective: design and build Sail SDP with all applicable Spark **4.2.1** SDP
  behavior covered and passing. Batch is the first milestone; streaming and CDC
  remain required. Do not redefine completion around the current passing subset.
- Sail implementation branch: `work/spark-declarative-pipelines` in
  `/Users/alexy/src/sail-pipelines-proposal`, at `96eb6d75fe13f1254af5fb1452d16abbd1fff446`.
  Starting Sail base: `0ba425c0331aee4dd4e9a280c6a793926fd0876e`.
- Design/evidence branch: `work/sail-declarative-pipelines` in
  `/Users/alexy/src/grust-sdp`. Evidence before this review brief is committed at
  `557a5ed03985f2ab0b8fb1d637761e518ffb8910`.
- Spark reference: `617618396087429b5627a86ce933bb0f5d6645cb` in
  `/Users/alexy/src/spark-sdp-4.2.1`; version 4.2.1 throughout.
- Recorded: `2026-10-29T16:31:56.621637+00:00`. These are snapshot claims, not claims about later HEADs.

## Read these first

| Document | What to review |
| --- | --- |
| [DESIGN.md](DESIGN.md) | Overall architecture, semantic contracts and batch → streaming → CDC ordering. Features described here are not automatically implemented. |
| [REVIEW.md](REVIEW.md) | Granular implementation commits, intended review boundaries, evidence and qualifications. This is the entry point for reviewing the code history. |
| [CROSSWALK.md](CROSSWALK.md) and [inventory](spark-4.2.1-inventory.json) | Exact upstream source registrations, covered assertions and outstanding work. |
| [STREAMING-REUSE.md](STREAMING-REUSE.md) | Source review and incremental streaming/Iggy outline; especially the durability gaps. |
| [EXECUTION-ERROR-DESIGN.md](EXECUTION-ERROR-DESIGN.md) | Current selected shared error design; extraction and transport are implemented, cast producers/codec/SQL activation remain pending. |
| [CATALOG-EXPRESSION-DESIGN.md](CATALOG-EXPRESSION-DESIGN.md) | Shared SQL/catalog resolution, source origins and prepare/commit boundaries. |
| [SQL-SOURCE-DESIGN.md](SQL-SOURCE-DESIGN.md) | Original SQL text preservation without changing TreeText's reconstruction contract. |
| [CATALOG-ACCEPTANCE.md](CATALOG-ACCEPTANCE.md) | Memory/LakeCat adapter profiles and limits of the provider evidence. |
| [BATCH-EVENT-DESIGN-HANDOFF.md](BATCH-EVENT-DESIGN-HANDOFF.md) and [FILE-SOURCE-DESIGN-HANDOFF.md](FILE-SOURCE-DESIGN-HANDOFF.md) | Known batch failure/event and ORC boundaries; unresolved design work. |

## What exists, and what does not

The batch control layer is functional: graph/output/flow registration, pipeline
SQL definitions, graph dependency/schema analysis, selection and batch execution,
private/persisted views, and catalog publication use Sail's planner and execution
services. SQL scope/configuration, identifier/error behavior and source preservation
have progressively stronger coverage. Review the individual receipts rather than
inferring full support for every option from this list.

The latest [transport receipt](evidence/96eb6d75fe13f1254af5fb1452d16abbd1fff446/gate.json) records:

- 257 affected Rust library tests: common 66, execution 151, Connect 40; no filters
  or ignored tests in these suites. Formatting, strict Clippy and CLI build pass.
- 246 selected Sail Python regressions and 67 pinned upstream Python executions
  pass against a freshly built CLI. The upstream Python set includes inherited
  and client-only tests; it is not the whole SDP execution acceptance suite.
- The retained catalog-expression probe remains **11 passed / 2 failed**. The
  remaining ANSI cast failures lack CAST_INVALID_INPUT/22018 metadata because
  the new structured cast producers are not activated yet.
- The broader ordinary-cast probe remains **4 passed / 20 failed**, with all
  mismatches retained. Decimal/temporal/overflow errors have different contracts;
  they must not all be labeled malformed numeric input.

The static inventory has **462 registrations**, including helper calls and
unexpanded parameter grids. **97 have assertion reviews; 365 remain unaudited.**
There are **59 partial behavioral ports**, not 59 fully passing Scala tests.
Within the 97 reviewed registrations, 38 remain unmapped. No original Scala suite
has been executed against Sail; internal Catalyst fixtures cannot simply run
unchanged inside a Rust server. Review whether the proposed assertion-by-assertion
porting and evidence process can meet the full original objective without silently
excluding internal, parameterized, failure, streaming or CDC behaviors.

Substantial batch acceptance remains: failure/event attribution, cancellation,
remaining view/catalog/schema/partition cases, ORC, and distributed qualification.
Streaming/Iggy runtime integration and CDC execution are **not implemented** in
this SDP branch.

## Implementation map and architectural constraints

Start with [the pipeline modules](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/mod.rs),
then inspect graph registration, SQL preparation, analysis, topology, selection,
schema merge, materialization and execution beside that file. Public tests live
under `python/pysail/tests/spark/pipelines`; upstream runners and inventories are
under `scripts/spark-pipelines-tests` in the Sail branch.

Review the shared boundaries as well as the pipeline module:

- `sail-sql-parser` / `sail-sql-analyzer`: pipeline syntax and original source spans.
- `sail-plan`: typed expressions, shared catalog resolution and scoped relation
  resolution. General SQL/catalog behavior belongs here or in the appropriate
  existing Sail component, with LakeCat one catalog adapter.
- `sail-common-datafusion`: shared error data/causes. `sail-execution`: existing
  task, worker and codec machinery. `sail-spark-connect`: protocol/error formatting.
- `sail-catalog` and existing table writers: shared catalog/provider behavior and
  publication; no LakeCat-only SQL rules or second execution engine.
- [Grust vendor provenance](/Users/alexy/src/sail-pipelines-proposal/vendor/grust-topology/SOURCE.json):
  the small dependency-free topology kernel is already extracted and imported.
  Its source pin is `fb18b27aa561ffb75a2da5a0f14f23a3cdfce6cd`.
  Do not import the whole Grust graph stack or its Sail adapter.

Preserve Sail's actor/service conventions, `PlanResolver`, `JobService`, catalog
interfaces and existing distributed codecs. Pipeline scheduling orders flows;
it must not become a second query-stage/task scheduler. Do not hold graph locks
across asynchronous analysis. Ephemeral session graph IDs must not become durable
flow identities. General catalog improvements belong in Sail; LakeCat provider
coverage and small reusable control primitives belong at their proper boundaries.

All changes must stay in small, human-reviewable logical commits. Reusable pieces
may be extracted from Grust/LakeCat and reimported there, but should have a small
Sail import footprint. Plans/reviews live in Grust, not Sail. No push, upstream PR,
release or external message is authorized by this review request.

## Streaming/Iggy: review this most closely

**Draft maturity:** source review plus integration outline, not a complete
implementation-ready checkpoint/state-machine design. Please identify the missing
decisions explicitly before endorsing an implementation sequence.

Pinned sources reviewed in [STREAMING-REUSE.md](STREAMING-REUSE.md):

| Source | Pin / local access |
| --- | --- |
| Private `lakehq/sail-iggy`, branch `codex/iggy` | `5816b9b2f3bd20cd124f24128b7e45818351bcc1`; `/Users/alexy/src/sail-iggy-sdp-review`. Its default main does not contain the integration. |
| Local Apache Iggy SDK/broker | `153fdf466aea94b7bcb90681ee7274f9f76ec00d` in `/Users/alexy/src/iggy`; inspect pinned Git objects because its working checkout is independently active. |
| LakeCat provider evidence | `27e18f390c450c187a34b1c3bb2037c26d107699`; `/Users/alexy/src/lakecat-sdp-gate`. |

The private Sail-Iggy branch uses DataFusion 54.0.0 and Iggy 0.10.1-edge.2;
the reviewed local SDK declares 0.11.1-edge.5 and current SDP Sail uses DataFusion
55.2.0. This is a deliberate API/codec port, not a cherry-pick qualification.
Broker tests from that branch were inspected as source, not rerun for current Sail.

The connector's feature-gated source/sink/format adapters and the mirror's
poll → commit → acknowledge recovery model are useful starting points. The mirror
commits rows and an application transaction version together in Delta, recovers
ambiguous outcomes from the durable cursor, then acknowledges the broker. Its
standalone SessionContext/QueryPlanner must not become a second Sail execution path.

Please review these contracts and return concrete counterexamples where they fail:

1. **Identity and state ownership.** Specify stable pipeline/flow/reset/attempt
   identities, versioned state, definition/schema compatibility and output mapping.
   Which small LakeCat CAS/replay/outbox primitives should be extracted, and which
   should remain catalog-specific? Keep pipeline control state outside Iceberg
   metadata and avoid a Sail → lakecat-sail dependency cycle. No such streaming
   control-state extraction is implemented yet.
2. **Repeatable input ranges.** Define a fixed per-partition available-data frontier
   for bounded runs, explicit offsets, partition incarnation, retention gaps,
   repartitioning and source growth. Explain replay for multiple sources and flows;
   output row count is not a source cursor after filters, joins or aggregates.
3. **Acknowledgment ordering.** The reviewed connector can store offset+1 before
   yielding a row when auto-commit is enabled. Durable SDP must not use that as a
   commit boundary. Distinguish next-offset state from Iggy's stored last-consumed
   offset. Use captured message positions/incarnations/ownership when acknowledging
   asynchronous work; audit OperationUncertain, LaneBlocked and ownership/history
   rejection against the pinned SDK.
4. **Sink capabilities and atomicity.** Identify the first supported transactional
   sink, its idempotency key and durable commit lookup. The mirror's Delta
   txn_app_id/txn_version support is not exposed by the reviewed Sail writer base.
   Specify the necessary writer/serialization changes. A checkpoint-marker flush,
   ordinary append followed by a manifest, or deterministic broker message ID is
   not by itself proof of exactly-once recovery. State the boundary per sink/flow
   rather than assuming a global transaction across every output.
5. **Fenced ownership.** The mirror assumes one active writer and has no fencing
   protocol. Specify takeover, lease expiry/renewal, stale-writer rejection and
   conditional progress updates. Determine whether the sink can fence an old writer
   after it has lost control-state ownership.
6. **Crash/recovery matrix.** Cover failure before intent, after intent, during
   execution, before commit, lost commit response, committed sink before progress
   update, progress before broker acknowledgment, failed acknowledgment, stale-owner
   resumption and reset during an in-flight attempt. Include restore of data/logs,
   control state and schema descriptors, not only a clean-process restart.
7. **Sail execution integration.** Reuse JobService, actors, cancellation and worker
   scheduling. The private Iggy physical nodes lack distributed codec arms; its
   unbounded repartition removal is a workaround to investigate, not a general
   partitioning rule to copy. Define backpressure and task failure behavior.
8. **Optional adapters.** Keep generic progress/commit/recovery independent of Iggy,
   its schema registry and lakehouse providers. Treat Iggy input and output delivery
   capabilities separately; do not promise transactional broker output without
   checking deduplication scope, retention and recovery behavior.

## CDC: review the semantic and durability plan

**Draft maturity:** the overall design has an SCD1 contract/outline. There is no
complete CDC processor/auxiliary-state design or implementation in this SDP branch.
The pinned PySpark 4.2.1 create_auto_cdc_flow API supports SCD type 1; do not infer
SCD2 support or requirements from another product/version.

Read the pinned Spark `sql/pipelines` sources and suites rather than assuming that
a MERGE statement implements CDC. Start with `autocdc/ChangeArgs.scala`,
`ScdBatchValidator.scala`, `Scd1BatchProcessor.scala`, `Scd1ForeachBatchHandler.scala`,
and the AutoCdcFlow/ChangeArgs/Scd1BatchProcessor/Scd1BatchProcessorMerge/
Scd1ForeachBatchHandler suites. Also inspect graph-level AutoCdcAuxiliaryTable,
AutoCdcScd1AuxiliaryTableDurability, AutoCdcScd1FullRefresh and AutoCdcScd1KeyDrift
suites at the same reference SHA. Their coverage is still outstanding.

Please address:

1. Exact key and sequence-expression validation, ordering/ties, out-of-order/late
   changes, deletes, tombstones, null semantics and included/excluded columns.
   Determine required behaviors from the 4.2.1 assertions, including rejected inputs.
2. Target/auxiliary-state schemas, reserved names, schema evolution and key drift.
   Which state must remain after a target row is deleted to reject an older update?
   What retention/garbage-collection rule is actually supported by Spark's contract?
3. Atomic recovery when target data and auxiliary sequence/tombstone state are
   stored separately. Define the failure/restore matrix when only one commit is
   visible; do not assume two successful writes are one transaction.
4. Interaction with stable source ranges, sink transaction IDs, fenced ownership,
   reset generations, selective/full refresh, cancellation and replay. Specify when
   broker acknowledgment is safe relative to CDC target and auxiliary durability.
5. What can reuse Sail's existing MERGE and catalog/writer machinery, what requires
   new stateful processing, and how to keep that processing reusable across sources
   and catalog providers. Avoid implementing only the simple in-order upsert case.
6. An assertion-preserving CDC test inventory and incremental commit plan, including
   data/auxiliary crash consistency, duplicate delivery, deletes followed by stale
   updates, restart, full refresh and definition/schema changes.

## Review outputs requested

Return a prioritized findings list, with source/commit or test evidence and a
concrete failure scenario. Separate defects in implemented code from unresolved
draft decisions. State assumptions and evidence limits. Please include:

- Whether the current Sail architecture and dependency boundaries are appropriate.
- The minimum complete streaming contract that supports later CDC without a redo,
  plus decisions that must precede implementation and alternative tradeoffs.
- The critical CDC correctness/durability decisions and a realistic work estimate
  by phase; do not substitute a percentage derived from passing test counts.
- Missing source assertions, overly weak tests, accidental skips/normalizations,
  nondeterministic error attribution or unsupported catalog/delivery claims.
- A sequence of small reviewable commits and which need Astra design work versus
  implementation that Sol can carry out from a settled design.

The agreed order remains batch → streaming → CDC. Flag necessary preparatory
work early, but do not silently start a new streaming/CDC design or implementation
phase. The operator requested notice before each new design phase to switch to
Astra. Do not weaken retained failing assertions, count unsupported cases as passes,
or mark the full goal complete from the current selected suites.

---

# Fable review

Reviewer: Claude Fable 5.1. Written 2026-10-29T16:57:03Z against the pins in the brief:
Sail `96eb6d75fe13f1254af5fb1452d16abbd1fff446`, Grust evidence
`557a5ed03985f2ab0b8fb1d637761e518ffb8910`, Spark `617618396087429b5627a86ce933bb0f5d6645cb`,
`lakehq/sail-iggy` `5816b9b2f3bd20cd124f24128b7e45818351bcc1`, Apache Iggy
`153fdf466aea94b7bcb90681ee7274f9f76ec00d` (read through pinned Git objects only),
LakeCat `27e18f390c450c187a34b1c3bb2037c26d107699`.

**How this was produced, and its limits.** Every claim below is from reading
source at those pins, in the main session or through four read-only scans
(Iggy SDK, Sail streaming/writer/JobService boundaries, LakeCat control
primitives, the Spark Auto CDC test suites). No code was built, no test was
run, no gate was rerun. Where a scan reported "not found" or "inferred" I say
so. The implemented-code reading covered `pipelines/mod.rs`, `execution.rs`
and the agent's summaries of `materialize.rs`, `graph.rs` and the shared
boundaries; `analysis.rs`, `sql.rs`, `schema_merge.rs` and the Python tests
were not read line by line, so the absence of findings there is absence of
reading, not a clean verdict. Per the brief, nothing here authorises a push,
PR, release, message or the start of a streaming/CDC implementation phase.

## 1. Verdict in brief

- **Batch architecture and dependency boundaries are appropriate.** The
  pipeline module stays a control layer over `PlanResolver`, catalog
  publication and `JobService` (`execution.rs:96-113`), the topology kernel is
  the only Grust import, and Spark's own handler mutates the session's current
  catalog and database exactly as Sail's does (`PipelinesHandler.scala:213-214`),
  so that is not a defect. No correctness defect was found in the implemented
  code I read; the findings against implemented code (section 2.1) are
  prerequisites, not bugs.
- **The streaming draft is a source review, as it says.** Sections 4 and 5
  turn it into a contract. The single most consequential recommendation is
  structural: SDP streaming in 4.2.1 is `Trigger.AvailableNow`, so each
  microbatch should be an ordinary bounded batch plan over explicit ranges,
  run through the batch path that already writes Delta and Iceberg, not
  through Sail's streaming rewriter, which today rejects joins, aggregates and
  repartition and can only sink to console, file or noop
  (`sail-plan/src/streaming/rewriter.rs:51-104`).
- **CDC is fully specified by the Spark source** (section 6). Its durability
  does not need a two-table transaction: Spark relies on intent-before-execute
  replay plus merges whose every clause is gated on an inequality that makes
  replay a no-op. I checked that argument clause by clause and it holds for a
  single fenced writer. What Sail must add that Spark does not test is crash
  injection between the two merges and between the merges and progress.
- **Reuse verdicts.** Port the mirror's _protocol_ (poll, commit, verify,
  acknowledge) and its test scenarios; do not port its version-as-offset
  inequality or its scalar acknowledgment. Do not extract control-state
  primitives from LakeCat: nothing there is standalone (section 2.2, B9), and
  a dependency-free model is smaller to write than to carve out. Iggy is the
  third source to build, not the first, because every Spark streaming and CDC
  fixture reads from an in-memory stream or another table.

## 2. Findings, most severe first

Severity is about what breaks if the item is ignored. "Defect" means wrong
today; "gap" means missing for the stated goal; "draft" means an unresolved
design decision in the reviewed documents.

### 2.1 Implemented code and reviewed sources

| #                           | Where                                                                                                                                                                      | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Failure scenario if ignored                                                                                                                                                                                                                                    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1 (draft, high)            | STREAMING-REUSE.md §"What is reusable"; `sail-iggy-mirror/src/coordinator.rs:124-140`, `delta_sink.rs:475-513`                                                             | The mirror decides "already committed" by `stored_version >= batch_version` where the version **is the partition high-water offset**. That inequality is sound only because one writer commits contiguous ranges in order from a single cursor. It must not be generalised to SDP flows with several sources, joins or aggregates.                                                                                                                                                            | A flow over two partitions keyed by one of their offsets: a later commit on partition A makes a lost commit on partition B look committed; rows are skipped and the broker is acknowledged. Section 5.4 gives the safe form (version = batch sequence number). |
| A2 (gap, high)              | `sail-data-source/src/formats/iggy/reader.rs:178-190` (private branch)                                                                                                     | Reader stores `offset + 1` before yielding the row when `auto_commit` is set. Already recorded in STREAMING-REUSE; add that the SDP adapter must contain **no** `store_offset` call at all, because the pinned SDK's `get_consumer_offset` "can be a backup that lags the partition's primary" and the server commits `PollingMessages` auto-commit "before the caller receives the messages" (`core/common/src/traits/message_client.rs`). The broker offset is advisory in both directions. | A restart that reads the broker offset to choose `start` can skip a batch (ahead) or duplicate one (behind).                                                                                                                                                   |
| A3 (gap, high)              | STREAMING-REUSE.md §"Incremental implementation boundaries" item 6; Iggy pin `core/configs/src/configs_impl/file_provider.rs` (`system.message_deduplication` → `Removed`) | Server-side deduplication by message id has been **removed** at the pinned Iggy. Only per-session request-id dedup within a window remains (`core/consensus/src/client_table.rs`, `RequestTooOld`), and a direct producer splits a batch into sequential requests with no cross-chunk atomicity. The branch's "deterministic message ID" cannot deliver exactly-once output.                                                                                                                  | An Iggy output adapter claiming exactly-once on message ids duplicates on any application-level resend. Output stays at-least-once (section 5.8).                                                                                                              |
| A4 (gap, high)              | Iggy pin `core/partitions/src/iggy_partition.rs` `disk_poll_start`, and no low-watermark field in `Partition` stats                                                        | Polling an offset that retention already removed **silently resumes at the first retained segment**; there is no error and no first-available API. The scan reported this as inferred from code, with doc text ("evicted cursors resume from the earliest retained messages") in support.                                                                                                                                                                                                     | Without the mirror's `first.offset > expected_start` check (`model.rs:99-108`) a retention gap is read as a normal batch and the gap is never reported. Keep that check as the only detector, and keep it fail-closed.                                         |
| A5 (gap, medium)            | Sail `crates/sail-delta-lake/src/transaction/mod.rs:1047-1117`, `snapshot/mod.rs:745`                                                                                      | `CommitData` can carry `Txn` actions and the snapshot exposes `transaction_version(app_id)`, but the `with_application_transaction` setters are commented out, no write option reaches them, and nothing calls the accessor. Conflict detection on a concurrent commit to the same app id fires only if the transaction declares that app id as read (`conflict_checker.rs:530-539`), and non-blind-append commits get zero retries (`mod.rs:1357-1364`).                                     | A fenced-out writer's late commit of batch `b` lands beside the new owner's commit of `b`; rows are duplicated. Section 5.4 names the three writer changes.                                                                                                    |
| A6 (gap, medium)            | Sail `pipelines/execution.rs:41-92`                                                                                                                                        | Flow execution is strictly serial in topological order with no concurrency limiter. DESIGN contract 4 says independent flows may run concurrently; for batch this is a performance gap, for streaming it is a correctness-of-progress gap because each streaming flow is a long loop.                                                                                                                                                                                                         | Two streaming tables in one pipeline: the second never starts until the first drains its frontier; with a slow source the run never reaches the second. The scheduler must run ready flows concurrently (bounded) before the first streaming flow is added.    |
| A7 (observation)            | Sail `pipelines/mod.rs:149-153`                                                                                                                                            | `storage` is required but unused, and only checked non-empty; Spark validates it as a path (`PipelineUpdateContextImpl.validateStorageRoot`). Fine for batch; it becomes the pipeline's durable identity in section 5.2, so validate it then.                                                                                                                                                                                                                                                 | —                                                                                                                                                                                                                                                              |
| A8 (verified, not a defect) | Sail `pipelines/mod.rs:167-171`; `sail-execution/src/driver/output.rs:65,127`                                                                                              | Cancellation drops the run future and hence the `JobService` stream; the driver observes `sender.closed()` and records `Canceled`. Correct for batch. The streaming loop must additionally guarantee it never reaches progress or acknowledgment after a cancel (section 5.6).                                                                                                                                                                                                                | —                                                                                                                                                                                                                                                              |
| A9 (gap, medium)            | Sail `sail-common-datafusion/src/streaming/source.rs:15-48`, `event/marker.rs:29`                                                                                          | `StreamSource` has no offset, frontier or commit concept; `FlowMarker::Checkpoint` has no producer; `checkpointLocation` is never read; `StreamingQueryManager` persists nothing. This confirms DESIGN's "existing streaming query handles alone do not supply SDP checkpoint semantics" and is the reason for recommendation 4.1.                                                                                                                                                            | —                                                                                                                                                                                                                                                              |

### 2.2 Draft decisions the brief asked to be made explicit

| #   | Brief item                     | Decision needed                                                      | Recommendation (section)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --- | ------------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1  | 7 (execution shape)            | Streaming rewriter and unbounded nodes, or bounded microbatch plans? | Bounded plans (4.1).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| B2  | 1 (identity)                   | What is the pipeline's durable identity?                             | The `storage` URI; flow key = destination path + flow name, Spark's layout (5.2).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| B3  | 1 (state ownership)            | Where does control state live?                                       | JSON records under `<storage>/_checkpoints/…` written with conditional puts; lease beside them (5.4, 5.5). Alternatives and why not: 4.3.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| B4  | 4 (first sink)                 | Which sink first, and what is its key?                               | Delta append with `txn {app_id, version=b}`; MERGE commits carry the same action for CDC (5.4). Iceberg second via snapshot summary + ref assertion.                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| B5  | 2 (ranges)                     | Frontier capture and range model                                     | Per-partition `[start, end)` with incarnation, captured once per run, persisted in the run record (5.3).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| B6  | 3 (acknowledgment)             | What is acknowledged, when, and with what                            | `store_position` with the captured `PartitionContext`, after progress, best effort (5.8).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| B7  | 5 (fencing)                    | Lease granularity and sink-side fencing                              | Lease per flow generation, epoch in every store write; sink fencing only where the sink commit is conditional on the commit key (5.5).                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| B8  | 2, 6 (retention gap, restores) | Default policies                                                     | Fail closed on gap, incarnation change, and any store/sink disagreement; explicit per-flow override recorded as an event (5.3, 5.6).                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| B9  | 1 (LakeCat extraction)         | Which primitives to extract                                          | None now. LakeCat's CAS is by expected pointer value inside Iceberg record types (`lakecat-store/src/records.rs:219-230`, `memory.rs:511`), its version CAS lives in `publish_model`, its idempotency records are keyed per table, and it has no lease, epoch or retention anywhere (`governed_scan.rs:80` is the only "lease" mention). `lakecat-core`/`lakecat-store` have no Sail dependency but pull tokio and the catalog records. Write the ~300-line model in Sail; LakeCat may reimport it later without a cycle because LakeCat already depends on Sail crates, not the reverse. |
| B10 | 8 (adapters)                   | Source order                                                         | In-process test source, lakehouse-table version ranges, then Iggy (5.3).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| B11 | CDC 5                          | MERGE substrate for tests                                            | Sail MERGE exists for Delta and Iceberg only (`sail-plan/src/resolver/command/merge.rs:43,208-211`), not for memory tables; Spark's suites use an in-memory row-level catalog. Run Sail's CDC suites over Delta tables in a temporary location (6.4).                                                                                                                                                                                                                                                                                                                                     |
| B12 | CDC 1                          | Dedup ties                                                           | Deterministic tie-break by source position, declared as a choice inside Spark's "undefined" (6.1).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |

### 2.3 Evidence weaknesses

- **E1.** 365 of 462 registrations unaudited; 59 partial ports; 38 unmapped
  among the 97 reviewed (brief). The CDC suites add **170 executed cases**
  (section 6.3), none mapped, and the streaming-table graph and Connect suites
  are not yet inventoried at assertion level; the crosswalk totals will grow,
  not shrink, before they can fall.
- **E2.** REVIEW.md:304-305 records that the streaming probes "encountered a
  missing source during resolution; their null structured condition does not
  establish streaming-query validation". That is an accidental skip to keep
  visible: those probes currently pass for the wrong reason.
- **E3.** The Spark CDC suites contain **no crash or partial-failure test**;
  the replay argument lives in a comment (`Scd1ForeachBatchHandler.scala:63-67`)
  and two idempotency tests (MergeSuite "is idempotent across a microbatch…").
  Sail cannot port crash coverage; it must write it (6.4).
- **E4.** Spark's graph fixtures run with `PIPELINES_MAX_FLOW_RETRY_ATTEMPTS = 0`
  and feed later runs by `addData` on the **same** `MemoryStream`
  (`AutoCdcGraphExecutionTestMixin`). Sail's in-process test source must
  support "same stream, more data, new run, same flow name" or six-run cases
  such as HandlerSuite "reconciles out-of-order events when ExcludeColumns
  hides the sequencing column" cannot be ported faithfully.
- **E5.** The sail-iggy branch targets DataFusion 54 and Iggy 0.10.1-edge.2;
  the pinned SDK is 0.11.1-edge.5 with VSR consensus, new error codes
  (`OperationUncertain` 14006, `LaneBlocked` 14007, `OperationNotRetained`
  14008, `HistoryUnavailable` 87, `ConsumerGroupPartitionNotOwned` 5009) and
  removed message-id dedup. Treat its broker tests as scenario lists only, as
  STREAMING-REUSE already says.
- **E6.** Retained cast probes (11/2, 4/20) are correctly kept failing. Nothing
  in this review changes them.

## 3. Architecture and dependency boundaries

Appropriate, with three adjustments that should be made before streaming:

1. **Flow concurrency** (A6) in the batch scheduler, with the same bounded
   concurrency and stable diagnostic order that DESIGN contract 4 requires.
2. **A control-state module with no DataFusion, Arrow, Iggy or catalog types**:
   the identities of 5.2, the record of 5.4, a `ControlStore` trait with
   `read`, `cas_write(expected_version, epoch)` and lease operations, an
   in-memory implementation for tests, and property tests for the CAS/epoch
   rules. Place it as a small crate in the Sail workspace (it is runtime, not a
   plan or protocol concern); the pipelines module and later the mirror import
   it. Nothing from Grust or LakeCat is needed for it.
3. **A commit annotation on the write path** (`spec::WriteTo` and the row-level
   operation specs) carried to the Delta and Iceberg commit execs, plus a
   `lookup` on the lake source. This is the only writer change streaming needs
   and it is independent of Iggy.

What should stay out: the mirror's `SessionContext` and `MirrorQueryPlanner`
(already excluded by STREAMING-REUSE), the whole `sail-iggy-mirror` crate, any
Grust graph store, and any LakeCat crate. What must not happen: a pipeline
scheduler that schedules query stages, or physical nodes that commit control
state. Commit and progress are actions of the run actor, never of an
`ExecutionPlan`.

## 4. Decisions that must precede implementation

Each is a design decision for Astra; Sol can implement from any of the stated
options, but the option must be chosen first.

### 4.1 Microbatch shape: bounded batch plans

Spark 4.2.1 SDP runs every streaming flow with `Trigger.AvailableNow`
(`graph/TriggeredGraphExecution.scala:77`): capture the frontier once, process
it in microbatches, each an ordinary batch plan over explicit ranges, logged
as intent before execution and replayed with the same range after a crash
(`sql/core/.../runtime/MicroBatchExecution.scala:748-790`). No continuous trigger.

Recommendation: implement exactly that and nothing wider. Each microbatch is a
bounded `LogicalPlan` whose streaming inputs resolve, through the same
`RelationScope` mechanism `GraphScope` uses today, to **range-scan providers**
for the current intent; it is optimised and executed through `JobService` like
the batch flows in `execution.rs:70-100`. Consequences, each closing a brief
question:

- Joins, aggregates, windows, sorts and repartition work, because the batch
  planner handles them; the streaming rewriter rejects all of them today
  (`rewriter.rs:89-104`). The private branch's `RepartitionExec` removal
  (brief item 7) is not something to port; it is something this shape avoids.
- Delta and Iceberg are reachable as sinks; the streaming rewriter admits only
  console, file and noop sinks (`rewriter.rs:51-59`).
- Backpressure is the microbatch size (`max rows`/`max bytes` per partition per
  batch, recorded in the intent); memory is bounded by the plan.
- A task or worker failure fails the batch plan; the intent stands and the
  next attempt re-executes the same range. No partial progress exists.
- The only codec work is for the range-scan node, whose state is a descriptor
  plus `[start, end)` per partition: a `oneof` arm in
  `sail-execution/proto/sail/plan/physical.proto`, a decode arm and an encode
  branch in `proto/codec.rs`, and a round-trip test.

Alternative: extend Sail's `StreamSource`/`FlowMarker` path with offsets and a
checkpoint-marker producer. It would be the right base for a continuous
trigger, but 4.2.1 does not need one, the rewriter's gaps above would all have
to be closed first, and `DeltaWriteNode`/`IcebergWriteNode` would need streaming
sink variants. Defer until a continuous trigger is a requirement; the control
model of section 5 is unchanged by that choice.

### 4.2 First sink and its commit key: Delta

Delta has the plumbing (A5). Iceberg has the optimistic precondition
(`RefSnapshotIdMatch`, `sail-iceberg/src/physical_plan/commit/commit_exec.rs:122-128`)
but whether `sail-iceberg` can attach custom snapshot summary properties was
not verified; it is the second sink. Memory tables are not durable and say so.

### 4.3 Control-store backend: files under the storage root

Options considered:

- **Immutable versioned JSON documents** under
  `<storage>/_checkpoints/<catalog>/<database>/<table>/<flow>/<g>/`, where a
  write of record version `n+1` is `put_opts(..., PutMode::Create)` of
  `progress/<n+1>.json` and the reader takes the highest version present; the
  lease is `lease/<epoch>.json` written the same way. Create-if-absent is the
  compare-and-swap. This matters because the pinned `object_store` 0.13.2
  local backend returns `NotImplemented` for `PutMode::Update`
  (`object_store-0.13.2/src/local.rs:336-340`) but implements `PutMode::Create`
  through a hard link (`:372`), and the cloud backends implement `Create` with
  if-none-match. Matches Spark's layout, is sink-independent, never overwrites,
  and is testable on the local filesystem. **Recommended.** Old versions are
  retained; a later housekeeping commit may prune below the highest.
- **Delta `DomainMetadata` on the target table.** Would make progress and data
  one commit for Delta-only, single-sink flows, which is attractive; but a flow
  can have non-Delta sinks, intent must be written before the data commit
  anyway, and DESIGN already rules out putting control state in lakehouse
  table metadata. Not recommended.
- **Catalog table properties** (`SetTableProperties`): a Delta metadata commit
  per write, no CAS semantics across providers. Not recommended.

### 4.4 Source order

In-process test source with explicit positions and fault injection; lakehouse
table version ranges (for `STREAM(t)` and `readStream.table`); then Iggy.
Reason: every Spark streaming-table and CDC fixture is a `MemoryStream` or a
table read; Iggy is required for the product but exercised by none of the
upstream assertions.

### 4.5 Lease granularity

Per flow generation `(flow key, g)`, acquired by a run for every selected
streaming flow before its first intent and renewed by the run actor. Spark's
multi-pipeline suite lets two pipelines write one target under different flow
names (`AutoCdcScd1MultiPipelineSuite`, "two AutoCDC pipelines targeting the
same table…"), so the unit of exclusion is the flow, not the table or the
storage root.

### 4.6 CDC-specific decisions

Test substrate (B11), deterministic ties (B12), and whether sequencing types
beyond atomic types are supported in the first delivery (6.2, open question Q4).

## 5. The minimum complete streaming contract

This is the contract that supports CDC later without a redo. CDC adds a
per-batch handler and an auxiliary table; it adds nothing to identities,
ranges, commit, fencing or recovery.

### 5.1 Identities

| Identity               | Definition                                                                                                                                                                                    | Source of truth     |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| Pipeline               | The `storage` root URI from `StartRun` (required today in `pipelines/mod.rs:149-153`, unused). Spark derives every durable path from it (`graph/SystemMetadata.scala:41-60`).                 | the URI; no UUID    |
| Flow key               | `(qualified destination identifier, flow name)` rendered as `catalog/database/table/flow`, Spark's layout, so a storage root shared by Spark and Sail runs cannot collide.                    | pipeline definition |
| Reset generation `g`   | Integer; Spark's numbered checkpoint directory (`graph/State.scala:80-110`). Full refresh of the destination creates `g+1`; nothing under `g` is deleted.                                     | control store       |
| Batch `b`              | `0, 1, 2, …` within a generation; Spark's `batchId`. Strictly sequential: `b` cannot be intended until `b-1` is progressed.                                                                   | control store       |
| Attempt                | `(b, epoch e, attempt counter)`; diagnostics only, never a commit key.                                                                                                                        | control store       |
| Owner epoch `e`        | Monotone integer from the lease (5.5); every control-store write names the epoch it expects.                                                                                                  | control store       |
| Definition fingerprint | Hash of the canonical resolved plan text, output schema, ordered source descriptors, and for CDC the keys, sequencing expression, delete condition and selection. Stored once per generation. | control store       |
| Sink commit key        | `(pipeline, flow key, g, b)`, rendered per sink (5.4).                                                                                                                                        | the sink            |

Graph UUIDs from `CreateDataflowGraph` appear nowhere here (DESIGN contract 1).

Compatibility when the fingerprint changes without a reset: plan text and
source descriptor changes are allowed (Spark re-analyses every run); an output
schema change is allowed only if the batch phase's schema merge accepts it; a
CDC key or sequencing-type change is `AUTOCDC_INVALID_STATE.KEY_SCHEMA_DRIFT`
(6.2); a changed _source identity_ under the same flow key (another
stream/topic, another table UUID behind the same name) is an error unless the
user resets, because committed offsets would be meaningless.

### 5.2 Repeatable input ranges

A source adapter exposes three operations to the control loop and nothing else:

1. `describe()` → an opaque serialisable descriptor and the partition list, each
   partition with an **incarnation** (Iggy: `PartitionContext.incarnation`,
   "metadata creation revision of the partition, changes when the numeric
   partition id is reused", `core/binary_protocol/src/primitives/partition_history.rs`;
   lakehouse table: table UUID, one partition; files: directory URI).
2. `frontier(partitions)` → end position per partition now. This is Spark's
   `prepareForTriggerAvailableNow`. Called once per run before the first intent
   and persisted in the run record; later batches in the run read their end
   from that record, never from the source again.
3. `scan(partition, incarnation, start, end)` → a bounded `TableProvider`
   yielding exactly `[start, end)` or failing. It fails closed on a retention
   gap (first returned offset > `start`), on a non-contiguous page, and on an
   incarnation mismatch, as `MirrorBatch::try_new` does (`sail-iggy-mirror/src/model.rs:89-130`).
   For Iggy this post-hoc check is the **only** detector (A4).

The intent for batch `b` holds, per source and partition, `[start, end)` with
`end = min(frontier, start + max_per_partition)`. All sources of a flow advance
in one intent; a join or union of two streams is one batch over two ranges.
Replay re-plans the same ranges and nothing else, so output row counts never
enter progress (brief item 2). Nondeterministic expressions change replayed
content but not ranges; that is Spark's contract too, and the sink commit key,
not content, decides idempotency.

Partition changes between runs: new partitions start at the source's earliest
position and enter the next intent with their incarnation; a partition that
disappears while it has an unprogressed intent is an error; a changed
incarnation is an error unless reset. Iggy topics with `partition_resize_policy
= mutable` "do not guarantee per-key ordering across layouts" (pin,
`core/common/src/traits/partition_client.rs`); SDP should document that it
inherits that.

Skipping a retention gap is an explicit per-flow option recorded in the
control store and reported as an event, never a default.

The second source Sail needs is not Iggy (4.4). A lakehouse table as a
replayable source (Delta commit versions, Iceberg snapshot ids, append-only
reads, with the table UUID as incarnation) must exist for the Spark suites to
run at all.

### 5.3 Control record

Per `(flow key, g)`, written only by compare-and-swap on the record version
with the epoch as a precondition (realised as create-if-absent of the next
version file, 4.3):

```
FlowProgress {
  generation: g, epoch: e, fingerprint,
  run: Option<{ run_id, frontier per source/partition }>,
  committed_batch: Option<b>,                    // last b whose sink commit is confirmed
  intent: Option<{ b, ranges per source/partition, created_at }>,
  acknowledged: positions per partition          // best effort
}
```

### 5.4 Commit protocol per flow and batch

1. **Intent.** CAS-write `intent = {b, ranges}` with `b = committed_batch + 1`.
   An existing intent is reused unchanged; no new frontier is computed for it.
2. **Execute** the bounded plan through `JobService`, with the commit key
   attached to the sink write.
3. **Confirm.** On success, or on any ambiguous outcome (timeout, lost
   response, restart), `lookup(flow, g)` on the sink returns the highest
   committed `b'`. `b' == b`: committed. `b' == b-1`: not committed, repeat 2.
   `b' > b`: the control store was bypassed; abort with a fencing error.
4. **Progress.** CAS-write `committed_batch = b, intent = None`.
5. **Acknowledge** the source with the captured positions of the last record
   per partition. Failure is logged and retried next run; it never affects 1–4.

Why `b' >= b` is safe here while the mirror's inequality is only conditionally
safe (A1): the version is the batch sequence number and batches are strictly
sequential per flow, so "a later batch is committed" implies "this batch is
committed" by construction, for every source shape.

**Delta rendering.** `app_id = "sdp/<pipeline>/<flow path>/<g>"`, `version = b`,
emitted as the `txn` action on the append commit and on each MERGE commit. The
three writer changes: (a) a commit annotation on `spec::WriteTo` and the
row-level operation spec, carried to `DeltaCommitExec` and set through the
currently commented-out `with_application_transaction`
(`transaction/mod.rs:1109-1117`); (b) `lookup` through `DeltaSnapshot::transaction_version`
(`snapshot/mod.rs:745`); (c) the commit must declare the app id as **read**, so
that `conflict_checker.rs:530-539` raises `ConcurrentTransaction` when another
writer committed the same app id in between, and a conflict on a MERGE (zero
retries, `mod.rs:1357-1364`) must surface as "re-run confirm", not as a retry.
The mirror's rule that the target must not set
`delta.setTransactionRetentionDuration` (`delta_sink.rs:142-160`) carries over:
an expired `txn` makes `lookup` lie.

**Iceberg rendering.** Commit key in the snapshot summary; commit with
`RefSnapshotIdMatch` against the snapshot that was read for `lookup`, so the
check and the commit are one conditional step. Verify summary-property support
in `sail-iceberg` first (Q5).

**Memory tables.** No `lookup`; a pipeline whose sink is a memory table is not
durable, and tests that need durability use a lakehouse sink.

### 5.5 Fenced ownership

A lease per `(flow key, g)`: `{owner_id, epoch, expires_at}`. Acquire by CAS
from absent or expired with `epoch + 1`; renew by CAS with the same epoch; every
`FlowProgress` write names its epoch and fails on mismatch; losing the lease
stops the loop before the next intent.

That fences the control store. It does not fence the sink: a writer that lost
the lease between steps 2 and 3 may still commit `b`. Whether that is harmless
depends on the sink:

- If the sink commit is conditional on sink state read in the same attempt,
  and the condition covers the commit key (Delta `txn` read-set, Iceberg ref
  assertion after reading the summary), two writers cannot both commit `b`.
  The loser gets a conflict, re-runs `lookup`, sees `b` committed, adopts it.
  Adoption is correct because the content was computed over the same ranges.
- If the sink only appends and writes a marker afterwards, both appends land
  and rows are duplicated. That is the "manifest after an append" case, and
  the reason a sink without a conditional commit cannot be declared exactly-once.

The source side needs no fencing for correctness: the control store chooses
`start`. Iggy fences consumer-group offsets by `(client_id, session, generation)`
(`core/partitions/src/iggy_partition.rs:1119`), but standalone consumers have
no fencing at the pin; SDP uses a standalone consumer named per flow and
treats a refused acknowledgment as advisory (5.8).

Takeover test: A acquires, intends `b`, pauses; B acquires after expiry with
`e+1`, executes and progresses `b` and `b+1`; A resumes and tries to commit `b`
and then progress. Required: the sink rejects A or A's lookup shows `b+1` and
A aborts; A's progress CAS fails on epoch; the target holds each row once.

### 5.6 Crash and recovery matrix

"Store" is the control record, "sink" is `lookup`, "ack" the source position.
Each row is one test with fault injection at that point, first against the
in-process source and sink, then Delta, then Iggy.

| Failure point                               | Store                      | Sink         | Recovery                                                                                              |
| ------------------------------------------- | -------------------------- | ------------ | ----------------------------------------------------------------------------------------------------- |
| before intent                               | committed `b-1`, no intent | `b-1`        | start `b`                                                                                             |
| after intent, before execution              | intent `b`                 | `b-1`        | re-execute `b` with stored ranges                                                                     |
| during execution (task, worker or process)  | intent `b`                 | `b-1`        | same; uncommitted files are the sink's orphan problem                                                 |
| sink commit sent, response lost             | intent `b`                 | `b` or `b-1` | lookup decides: progress, or re-execute                                                               |
| sink committed, died before progress        | intent `b`                 | `b`          | progress, then ack                                                                                    |
| progressed, ack failed or not sent          | committed `b`              | `b`          | ack next run; nothing replays because the store, not the ack, chooses `start`                         |
| stale owner resumes                         | epoch mismatch             | any          | abort before intent; a late sink commit is adopted or rejected per 5.5                                |
| full refresh while intent `b` exists in `g` | intent in `g`              | `b-1`        | `g+1` is created; `g`'s intent is abandoned; target truncated under the reset policy; CDC aux dropped |
| cancel between intent and commit            | intent `b`                 | `b-1`        | as "during execution"; cancel never acks                                                              |
| store restored to an older copy             | committed `b-k`            | `b`          | lookup shows `b > b-k+1`: abort with a fencing error naming both; never re-execute `b-k+1`            |
| sink restored to an older copy              | committed `b`              | `b-k`        | abort: store and sink disagree; operator reset to `g+1`                                               |
| definition or schema descriptor lost        | fingerprint missing        | any          | refuse unless the operator requests `g+1`                                                             |

Any disagreement between store and sink, in either direction, is a stop.

### 5.7 Sail integration

- **Run actor.** One actor per run (Sail `Actor` conventions, `sail-common/src/actor.rs:65-98`),
  holding lease renewal and the per-flow loops. The batch scheduler orders
  flows; a streaming flow's "execute" is the loop of 5.4 instead of one
  `WriteTo`. Flow concurrency (A6) comes first.
- **Planner.** A `RelationScope` entry per streaming input resolving to the
  range-scan provider for the current intent, as `GraphScope` resolves
  graph-local names today.
- **Writer.** The commit annotation and `lookup` of 5.4.
- **Distributed.** The run actor lives on the driver; workers run range scans
  and writes; `DeltaCommitExec` already pins to the driver
  (`job_graph/planner.rs:766-777`). Range-scan nodes get codec arms and
  round-trip tests. A worker failure fails the batch plan, nothing else.
- **Cancellation.** Dropping the job stream cancels the job (A8); the loop
  must additionally check the cancel signal before steps 4 and 5.
- **Events.** Per-flow intent/commit/progress/ack events through the existing
  `PipelineEvent` stream, alongside the batch failure/event work already
  handed off.

### 5.8 Iggy as an optional input adapter

Over the pinned SDK (`0.11.1-edge.5`):

- Consumer built with `AutoCommit::Disabled` (the builder default) and
  `PollingStrategy::offset(start).with_context(ctx)`; no `store_offset` in the
  scan path (A2).
- `scan` checks the first returned offset against `start` (A4) and the
  `PartitionContext.incarnation` against the intent.
- Acknowledge with `store_position(ReceivedMessage::position())` so the commit
  carries the captured incarnation and owner context. Handle: `HistoryUnavailable`
  (87, partition recreated) and `ConsumerGroupPartitionNotOwned` (5009) → drop
  the position, do not retry, report; `OperationUncertain` → `resolve_operation`,
  then treat as done or retry; `LaneBlocked` → resolve the blocker, resend;
  `OperationNotRetained` → unknown, re-ack next run. All are safe because the
  stored offset is inclusive and advisory.
- Retention consequence worth documenting: the broker never deletes past the
  minimum committed consumer offset (`remove_sealed_segments_up_to`), so an
  SDP consumer that never acknowledges pins retention forever, and a reset to
  `g+1` should delete or re-store the flow's consumer offset deliberately.
- Topic `durability`/`consumer_offset_durability` (`Replicated` vs `Persisted`)
  decide whether an acknowledged send or store survives a quorum restart;
  record the topic's settings in the source descriptor and in evidence.

Output to Iggy is at-least-once (A3): per-session request dedup within a
window, base-offset-only confirmations, chunked sends without cross-chunk
atomicity. Claim nothing stronger in docs, events or tests.

## 6. CDC: Spark 4.2.1 SCD1 on the streaming contract

### 6.1 The contract, read from source

All statements are from the pinned `sql/pipelines` sources. Paths are relative
to `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/`.

**Execution shape.** `FlowPlanner.plan` turns an `AutoCdcMergeFlow` with
`ScdType.Type1` into `Scd1MergeStreamingWrite` (`graph/FlowPlanner.scala:80-104`);
`Type2` raises `AUTOCDC_SCD2_NOT_SUPPORTED`. `startStream` runs the source
change feed as a streaming query with `foreachBatch`, trigger `AvailableNow`
and the flow's versioned checkpoint directory; each microbatch goes to
`Scd1ForeachBatchHandler.execute(batch, batchId)` (`graph/FlowExecution.scala:630-660`).
CDC therefore inherits section 5 unchanged: intent before execution, replay of
the same `batchId` with the same range, no second execution of a progressed batch.

**Per-batch pipeline**, in the only order Spark says is correct
(`autocdc/Scd1BatchProcessor.scala`, `reconcileMicrobatch`):

| Step                           | Rule                                                                                                                                                                                                                                       | Exactness a port must keep                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Validate (`ScdBatchValidator`) | Sequencing type orderable; no null sequence; no null in any key.                                                                                                                                                                           | One aggregation pass; errors `AUTOCDC_MICROBATCH_VALIDATION.NON_ORDERABLE_SEQUENCE` (`dataType`), `NULL_SEQUENCE` (`nullCount`), `NULL_KEY` (`nullKeyCounts` as `` `k`=n, … `` in key order), each with `tableName` (quoted three-part) and `batchId`; checked in that order; nothing written on failure.                                                              |
| Deduplicate                    | `groupBy(keys).agg(max_by(struct(*), sequencing))`.                                                                                                                                                                                        | One row per key with the largest sequence. Equal sequences: **undefined** which wins (BatchProcessorSuite "handles equal sequencing values"). Quirk pinned by a unit test: all-null sequences yield a null row (unreachable after validation).                                                                                                                         |
| Metadata                       | `deleteSequence = CASE WHEN deleteCondition THEN seq END`; `upsertSequence = CASE WHEN deleteSequence IS NULL THEN seq END`.                                                                                                               | Null or false condition is an upsert. Computed **before** selection. Both fields cast to the resolved sequencing type; an uncastable sequence is `DATATYPE_MISMATCH.CAST_WITHOUT_SUGGESTION`.                                                                                                                                                                          |
| Project                        | Drop the metadata column, apply include/exclude to user columns, re-append metadata last.                                                                                                                                                  | Matching honours `spark.sql.caseSensitive`; missing columns raise `AUTOCDC_COLUMNS_NOT_FOUND_IN_SCHEMA` with `schemaName`, `caseSensitivity`, `missingColumns` (user casing), `availableColumns`. Users cannot add or drop the metadata column.                                                                                                                        |
| Tombstone filter               | Left anti-join on keys where `greatest(deleteSeq, upsertSeq) < aux.deleteSeq`.                                                                                                                                                             | **Strict**: equal survives. Late upserts and stale deletes are both dropped. Any dominating tombstone row drops the event (duplicate aux rows are tolerated).                                                                                                                                                                                                          |
| Aux merge                      | `MERGE INTO aux ON keys`: (1) matched, incoming is a delete, `inDelete > auxDelete` → update metadata; (2) matched, incoming is an upsert, `inUpsert >= auxDelete` → delete the tombstone; (3) not matched, incoming is a delete → insert. | "Is a delete" = `deleteSeq IS NOT NULL AND (upsertSeq IS NULL OR deleteSeq > upsertSeq)`. Tied delete: no-op. Tied upsert: removes the tombstone. An upsert for an untracked key never touches aux. A delete is recorded even when the target has no row or a newer row (HandlerSuite "ignores a late-arriving lower-seq delete but still records the aux tombstone"). |
| Target merge                   | `MERGE INTO target ON keys`: (1) matched, `inDelete > tgtUpsert` → delete; (2) matched, `inUpsert >= tgtUpsert` → update all non-key microbatch columns and metadata; (3) not matched, `inDelete IS NULL` → insert all microbatch columns. | Delete wins **strictly** above; upsert wins at **greater or equal** ("arbitrary but deliberate": upserts beat deletes on ties). Key columns are never assigned. A delete for an absent key is a no-op here.                                                                                                                                                            |

**Schemas, names, properties** (`graph/FlowExecution.scala:325-440, 660-665`;
`autocdc/AutoCdcReservedNames.scala`; `graph/Flow.scala:250-397`):

- Reserved prefix `__spark_autocdc_`. A source column with that prefix, under
  the session's case sensitivity, is `AUTOCDC_RESERVED_COLUMN_NAME_PREFIX_CONFLICT`
  (`schemaName = "changeDataFeed"`), checked before selection; a key or selection
  naming one is `AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA` or `AUTOCDC_COLUMNS_NOT_FOUND_IN_SCHEMA`.
  A key absent from the source, or dropped by the selection, is
  `AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA` (`keyColumnName`).
- Metadata column `__spark_autocdc_metadata STRUCT<deleteSequence: T, upsertSequence: T> NOT NULL`
  with nullable fields, `T` the sequencing type resolved at flow setup. The
  **target carries it as a real, visible column**; readers see it, and a
  downstream MV in Spark's own test simply projects it away. A target created
  without it gets it appended by the schema merge on the first run; new user
  columns from later runs land **after** it (`StructType.merge` appends
  right-only fields).
- Auxiliary table `__spark_autocdc_aux_state_<target table>` in the target's
  catalog and database, schema `keys (declaration order) + metadata`, no data
  columns, created lazily at flow execution (never by a dry run), inheriting
  the target's provider; invisible to the graph. Properties
  `pipelines.autocdc.scdType = "SCD1"` and `pipelines.autocdc.keyColumnNames`
  (JSON array of unquoted names, written once, immutable). It is never evolved;
  a user-dropped aux table is transparently recreated.
- Key drift (`graph/FlowExecution.scala:505-605`), checked in the write's
  constructor when the aux table exists, after
  `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE` (a target format without row-level
  operations, e.g. parquet): errors `AUTOCDC_INVALID_STATE.AUXILIARY_TABLE_PROPERTY_MISSING`,
  `…_MALFORMED` (`rawValue`), `…_KEY_COLUMN_MISSING` (`keyColumnName`),
  `…KEY_SCHEMA_DRIFT` (`expectedKeySchema`/`recordedKeySchema` as DDL), in that
  precedence, all with `flowName` and `auxTableName`. Keys are compared as a
  set: same arity, names via the session resolver, `dataType.sameType`;
  reorder, nullability, metadata and quoting differences are **not** drift.
- Full refresh **drops** the aux table, truncates the target, replaces the
  target schema, and rolls the checkpoint directory
  (`graph/DatasetManager.scala:302-331`, `graph/State.scala:80-110`).
- Graph validation: one Auto CDC flow per target and no other flows
  (`AUTOCDC_MULTIPLE_FLOWS_TO_TARGET`); not into a temporary view
  (`INVALID_FLOW_QUERY_TYPE.AUTOCDC_RELATION_FOR_TEMPORARY_VIEW`); `ChangeArgs`
  rejects empty keys and multipart column names. Two **pipelines** may target
  one table under different flow names and share target and aux.
- Schema evolution across runs on the target: new nullable columns and
  broadened selections are added; narrowed selections and dropped source
  columns leave existing values and insert null; type changes are
  `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE`; dropped nested fields are
  `INCOMPATIBLE_DATA_FOR_TABLE.CANNOT_FIND_DATA`; a case-only name difference
  under case-insensitive resolution is `AMBIGUOUS_REFERENCE`.

**Answers to the brief's CDC questions 1–3:**

- _State that must remain after a target row is deleted so an older update is
  rejected:_ only the aux tombstone `(keys, deleteSequence)`. It is removed only
  by an upsert with `upsertSeq >= deleteSeq`, by a full refresh, or by the user
  dropping the aux table. There is **no time- or size-based garbage collection**
  in 4.2.1; Spark's comment lists "tombstone TTL" as future work. A TTL changes
  observable behaviour and would have to be a separately named option.
- _Atomicity between target and aux:_ Spark does not provide it. Per batch there
  are three durable writes (aux MERGE, target MERGE, checkpoint commit), each
  atomic alone. Correctness rests on intent-before-execute replay (section 5)
  plus merges whose every clause is gated on an inequality that the clause
  itself makes false or neutral. I checked `Scd1ForeachBatchHandler.execute`
  against each clause:

  | Crash after             | Replay: tombstone filter                                             | Aux merge                                                                                   | Target merge                                                                                               |
  | ----------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
  | nothing durable         | unchanged                                                            | first application                                                                           | first application                                                                                          |
  | aux MERGE only          | rows equal to a tombstone written by this batch survive (strict `<`) | no clause fires: `>` and `>=` fail against the just-written state; revived keys find no row | first application                                                                                          |
  | aux + target MERGE      | as above                                                             | no-op                                                                                       | upsert: `>=` re-updates with identical values; delete: key absent, `deleteSeq IS NULL` is false, no insert |
  | aux + target + progress | not replayed                                                         | —                                                                                           | —                                                                                                          |

  The one non-idempotency is the undefined `max_by` tie: equal-key, equal-sequence
  events may dedup to different winners on replay, and `>=` then installs the
  second winner. Inside the contract, but it makes crash tests flaky.
  Recommendation (B12): break ties by a stable source position and document it
  as a choice inside the undefined region.

- _Ties, pinned by the suites:_ within a batch, undefined; across batches an
  upsert equal to the stored upsert replaces the row, a delete equal to the
  stored upsert does not delete, a delete equal to a tombstone does not advance
  it, an upsert equal to a tombstone revives the key.
- _Nulls:_ null keys and sequences are rejected per batch, so key equality needs
  no null-safe operator; a null delete condition is an upsert; nulls in data
  columns are ordinary values.
- _Selection:_ applied after metadata derivation and before the tombstone join;
  the target's column set may be a strict superset of the microbatch's.

### 6.2 Mapping onto Sail

- **Where CDC lives.** A `cdc` submodule of the pipelines module: `ChangeArgs`,
  `ColumnSelection`, `UnqualifiedColumnName` with the exact error classes; a
  `Scd1BatchProcessor` that builds `LogicalPlan`s (dedup, metadata, projection,
  anti-join) with `PlanResolver`; a handler that runs validate → reconcile →
  aux MERGE → target MERGE as four `JobService` executions inside one streaming
  batch (5.4 step 2). The two MERGEs go through `resolve_command_merge_into`
  (`sail-plan/src/resolver/command/merge.rs:43`) and `plan_row_level_operation`,
  so they are ordinary Sail MERGEs on Delta or Iceberg (B11) and need no new
  stateful operator. What is new is the plan construction, the aux table
  lifecycle, and the error attribution.
- **Reserved names, properties and the aux table.** The aux table is created
  through `CatalogManager::create_table` with the target's provider and the two
  properties (`SetTableProperties` already exists); key drift reads them back
  through the catalog. The metadata column must be added to the target by the
  batch phase's schema merge, as Spark's `StructType.merge` does, so the
  "created without the column" and "new columns land after it" cases hold.
- **Commit keys.** Both MERGE commits carry the batch's commit key (5.4) so
  that a stale owner's MERGE conflicts and so that `lookup` can skip a batch
  whose two merges are already committed. Replay stays mandatory; the key is
  an optimisation and a fence, not the correctness mechanism.
- **DataFusion facts at Sail's pin (55.2.0):** there is no `max_by` aggregate
  (`datafusion-functions-aggregate-55.2.0` has none), so dedup is
  `first_value(struct(*) ORDER BY sequencing DESC, source_position)` per key,
  which gives the deterministic tie-break of B12 for free; `greatest` treats
  nulls as smaller than any value and returns null only if all are null
  (`datafusion-functions-55.2.0/src/core/greatest.rs:34-40`), which matches
  Spark, so the tombstone filter can use it directly. Still open (Q4):
  orderability of struct/array sequencing types. Where DataFusion cannot order
  a type Spark can, keep the Spark assertion failing rather than narrowing it.
- **Case sensitivity** comes from the flow's resolved `PlanConfig`, the same
  source the batch phase uses, for selection matching, key drift and reserved
  prefix checks.

### 6.3 Assertion inventory to port

170 executed cases across 13 suites at the reference SHA. The unit suites
(`autocdc/`) drive the processor directly and port to Rust tests over
`LogicalPlan` execution; the graph suites port to Sail pytest cases over a
Delta-backed temporary catalog with an in-process replayable source.

| Suite                                    | Cases | What it pins                                                                                                                                                                                              | Port target                                                                                |
| ---------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| ChangeArgsSuite                          | 22    | selection semantics, case handling, backticked and dotted names, multipart rejection, empty keys, parse errors                                                                                            | Rust unit                                                                                  |
| AutoCdcFlowSuite                         | 22    | flow schema with metadata last, resolved sequencing type, reserved-prefix and key-not-in-schema errors, SCD2 rejection, check order                                                                       | Rust unit + registration                                                                   |
| Scd1BatchProcessorSuite                  | 36    | dedup (incl. undefined ties, null quirks, composite and dotted keys, reserved-name collision → `AMBIGUOUS_REFERENCE`), metadata, projection, tombstone anti-join (strict `<`, duplicates, null tombstone) | Rust unit over plans                                                                       |
| Scd1BatchProcessorMergeSuite             | 20    | all six merge clauses, the tied-sequence asymmetry, idempotent re-application, case-sensitivity grid                                                                                                      | Rust over Delta MERGE                                                                      |
| Scd1ForeachBatchHandlerSuite             | 18    | validation order and parameters, end-to-end batch outcomes, six-batch out-of-order sequence, session case sensitivity                                                                                     | Rust over Delta                                                                            |
| AutoCdcAuxiliaryTableSuite               | 5     | JSON round-trip of key names, rejection of non-string arrays                                                                                                                                              | Rust unit                                                                                  |
| AutoCdcScd1SinglePipelineSuite           | 4     | single-run convergence, two targets in one pipeline, `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE` on parquet                                                                                                   | pytest                                                                                     |
| AutoCdcScd1TargetTableDurabilitySuite    | 3     | preloaded target rows, lazy aux creation, metadata column auto-added                                                                                                                                      | pytest                                                                                     |
| AutoCdcScd1AuxiliaryTableDurabilitySuite | 6     | cross-run tombstone suppression, aux key order and properties, aux dropped and recreated, special-character keys                                                                                          | pytest, multi-run                                                                          |
| AutoCdcScd1FullRefreshSuite              | 3     | aux dropped and target wiped on full refresh, selective refresh isolation                                                                                                                                 | pytest, multi-run                                                                          |
| AutoCdcScd1KeyDriftSuite                 | 13    | add/drop/swap/type-change drift, allowed reorder/nullability/quoting/case variants, property missing/malformed/key-missing                                                                                | pytest, multi-run                                                                          |
| AutoCdcScd1MultiPipelineSuite            | 5     | independent targets, shared target across pipelines with schema union, drift across pipelines                                                                                                             | pytest; one storage root per test (`utils/StorageRootMixin.scala:36`), distinct flow names |
| AutoCdcScd1SchemaEvolutionSuite          | 13    | nullable merges, add/narrow/broaden columns, type-change and nested-drop errors, case-only ambiguity, preserved extra columns                                                                             | pytest, multi-run                                                                          |

Fixture requirements that decide portability: the same in-process stream
receives more data between runs under the same flow name (E4); `PIPELINES_MAX_FLOW_RETRY_ATTEMPTS = 0`
so the first failure surfaces; targets are pre-created by DDL with the metadata
column last; `ConnectInvalidPipelineSuite` holds the two graph-validation
errors (`:659`, `:757`) and belongs to the batch crosswalk.

**Tests Sail must add that Spark lacks (E3):** crash injection after the aux
MERGE, after the target MERGE, after progress and before ack; duplicate
delivery of a batch; delete followed by a stale update across a restart;
takeover during a CDC batch (5.5); full refresh with an in-flight intent;
definition change (keys) detected before any merge.

### 6.4 CDC work by phase

Estimates are engineer-days for Sol working from a settled design, derived
from component counts, not from test counts; they exclude the streaming
prerequisites in section 7.

| Phase      | Content                                                                                                                       | Estimate |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------- | -------- |
| C0 (Astra) | Decisions: test substrate (B11), tie-break (B12), sequencing-type scope (Q4), metadata column placement in schema merge       | 1–2      |
| C1         | `ChangeArgs`/selection/unqualified names and error classes; protocol registration of auto-CDC flow details; graph validations | 3–4      |
| C2         | Batch processor plans: dedup, metadata, projection, tombstone anti-join; BatchProcessorSuite port                             | 4–6      |
| C3         | Aux and target MERGE construction through Sail MERGE, commit keys on MERGE commits; MergeSuite port                           | 4–6      |
| C4         | Validator, handler, batch wiring into the streaming loop; HandlerSuite port; crash-injection tests                            | 4–6      |
| C5         | Aux table lifecycle, properties, key drift, full refresh, schema merge of the metadata column; the seven graph suites         | 6–9      |
| C6         | Error attribution and events parity, crosswalk entries, book/changelog                                                        | 2–3      |

## 7. Commit sequence and ownership

Streaming first, in small reviewable commits, each with a stated boundary and
source-specific evidence as REVIEW.md does for batch. "Astra" marks design
work that must be settled before the commit; "Sol" marks implementation from
a settled design. Estimates as in 6.4.

| #              | Commit boundary                                                                                                                                                                            | Owner                                          | Estimate |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------- |
| S0             | Decisions 4.1–4.5 recorded in DESIGN.md/STREAMING-REUSE.md; this review's findings A1–A6 acknowledged                                                                                      | Astra                                          | 1–2      |
| S1             | Batch flow concurrency with bounded parallelism and stable diagnostic order (A6); batch tests only                                                                                         | Sol                                            | 2–3      |
| S2             | Control-state crate: identities, `FlowProgress`, lease, `ControlStore` trait, in-memory store, property tests of CAS/epoch rules; no I/O                                                   | Sol                                            | 3–4      |
| S3             | Object-store `ControlStore` with create-if-absent versioning and lease expiry; concurrent-acquirer tests on the local filesystem and one cloud backend                                     | Sol                                            | 3–5      |
| S4             | Delta commit annotation: enable `app_transaction`, write-option plumbing from `spec::WriteTo` and the row-level spec, `lookup`, app-id read-set conflict; duplicate-commit rejection tests | Sol                                            | 4–6      |
| S5             | In-process replayable source: positions, frontier, incarnation, retention-gap and failure injection; range-scan provider; scope resolution in the planner                                  | Sol                                            | 3–4      |
| S6             | Run actor and the loop of 5.4 for one append flow into Delta; full crash matrix of 5.6 with fault injection; cancellation                                                                  | Sol                                            | 5–8      |
| S7             | Pipeline integration: streaming TABLE outputs accepted, selection and full refresh → `g+1`, events, storage validation (A7); first Spark streaming-table cases                             | Sol                                            | 4–6      |
| S8             | Lakehouse-table source (Delta version ranges, table UUID incarnation) for `STREAM(t)` chains; multi-source intents; remaining streaming-table suites                                       | Astra for the version-range contract, then Sol | 5–8      |
| S9             | Iggy input adapter on the pinned SDK: bounded scan node with codec arms and round-trip tests, `store_position` acknowledgment with the error handling of 5.8, broker-backed tests          | Sol                                            | 6–9      |
| S10            | Iceberg sink: summary-property commit key with ref assertion (Q5)                                                                                                                          | Sol after Q5                                   | 3–5      |
| S11 (optional) | Iggy output adapter, documented at-least-once                                                                                                                                              | Sol                                            | 3–4      |
| C0–C6          | Section 6.4                                                                                                                                                                                | —                                              | 24–36    |

Rough totals: S1–S7 about 24–36 days, S8–S10 about 14–22, CDC 24–36. These
are estimates from the component list, with the usual caution that S4 and S9
touch external libraries whose behaviour at the pin was read, not run.

Per AGENTS.md, each commit is gated in a detached worktree, the verdict names
the commit, and the book and changelog follow any public-surface change.

## 8. Open questions

- **Q1.** Which cloud backends does Sail need `PutMode::Create` on, and do all of
  them honour it at `object_store` 0.13.2 (S3 needs a store that supports
  if-none-match; the local backend is verified).
- **Q2.** Delta `txn` read-set: confirm in the pinned delta-rs code that declaring
  the app id as read makes a concurrent commit with the same app id a
  `ConcurrentTransaction`, for both blind append and MERGE operations.
- **Q3.** Resolved while writing this review: no `max_by` in DataFusion 55.2.0,
  `greatest` ignores nulls; see 6.2.
- **Q4.** Which sequencing types can DataFusion order (struct, array, decimal,
  timestamp with zone)? Spark orders any `RowOrdering.isOrderable` type and the
  suites use longs, ints and a map (rejected). Decide the first delivery's scope
  and keep any excluded assertion failing.
- **Q5.** Can `sail-iceberg` attach custom snapshot summary properties on commit,
  and does the REST catalog path (LakeCat) preserve them?
- **Q6.** Can Sail's memory catalog register Delta tables at a temporary location
  so the CDC graph suites run without an external catalog? If not, the test
  substrate is a Delta directory catalog.
- **Q7.** Is a pinned Iggy server image available for broker-backed tests at
  `153fdf46…`, and which `durability`/`consumer_offset_durability` settings will
  the evidence record?
- **Q8.** `once` flows: Spark's Connect handler rejects `DefineFlow.once`, but the
  Scala suites use internal once flows that run once per checkpoint generation.
  Decide whether Sail models them internally for the streaming-table suites
  that depend on them, and record the decision in the crosswalk.

## Implementation updates after the pinned review snapshot

The snapshot above remains the historical 96eb6d75f review baseline. Subsequent
small commits are also available for review: [e28c27782](evidence/e28c27782604cc9f31ed6ec219114149d4ecdca8/gate.json) adds the shared
primitive cast and typed worker codec; [87a7c941d](evidence/87a7c941d30c952e6c928e1a6d2b4aec2b45abf6/gate.json)
activates them through PlanResolver. All thirteen catalog checks now pass; the
broader cast matrix is nineteen passes/five retained failures. The same 27 new
public instances pass on Spark 4.2.1 and Sail, with their pre-activation failure
recorded. The latest CLI passes 273 selected Python and 67 upstream executions.
Fable's appended review supplies detailed recommendations, not adopted Sail
implementation decisions. Streaming/Iggy and CDC runtime work is still pending;
these proposals need the announced design checkpoint before implementation.

Before adopting the streaming recommendations, verify cross-microbatch state and
allowed output modes for joins/aggregates/windows; batch-planner support alone
is not evidence of streaming parity. Recheck stale-writer behavior across reset
generations. The review's CDC parameter expansion is source analysis, not a new
runtime test verdict; the canonical inventory and execution counts above are
unchanged by preserving the review.


## Astra Ultra response and design improvements

Recorded: 2026-10-29T18:32:47.419473+00:00. This is the requested Astra Ultra review response to Fable's
source review. Fable's text above is preserved unchanged. The implementation
checked here is Sail `87a7c941d`, with Spark **4.2.1** source pinned at
`617618396`. The [evidence manifest](evidence/fable-astra-response/provenance.json)
records the exact pins, scripts, results and limitations.

The direction is realistic: preserve Sail's planner, job execution, catalog
abstractions and physical commit operators; add a small durable orchestration
layer around them. Batch remains the first delivery. Streaming and CDC are
substantial follow-on work, rather than a thin source adapter. Fable usefully
identifies the delivery sequence and recovery questions, but four proposed
shortcuts need correction before implementation: state-free microbatches,
separate lease/progress CAS, generation-only reset protection, and independently
leased CDC writers sharing a target. These are design amendments below, not
claims that Sail already implements streaming or CDC.

### 1. Bounded execution is a substrate, not stateful streaming semantics

**Adopt with a narrower initial contract.** Reusing bounded Sail plans for
stateless microbatches avoids building a second query engine. AvailableNow does
not remove cross-batch state. On Spark 4.2.1, two AvailableNow query runs with a
reused checkpoint and inputs `1`, then `2`, produce cumulative grouped sums
`1`, then `3`; reading only the second range as a batch produces `2`.
The [reference report](evidence/fable-astra-response/spark.json) retains this
experiment. It restarts the query in one Spark process; it is not a process-crash
or Sail state-store test.

A stream-stream join has the analogous problem: a left row in one batch can
match a right row in a later batch only if the required state survives. Ordinary
batch support for joins, aggregates, windows or sorts does not establish which
streaming forms and output modes are legal. Distinguish stream-static joins
from stream-stream joins and windowed aggregation from analytic window functions.

The initial runner should therefore admit only a documented stateless subset,
with explicit unsupported errors for other plans. Add stateful operators through
separate Spark-driven commits covering checkpointed operator identity, state
schema, output mode, watermarks, late data and eviction. Keep unsupported upstream
assertions visible as failures or unimplemented coverage, rather than removing
them from the acceptance denominator.

The execution envelope must already have a place for durable operator-state
versions and their completion receipts. Pin each source range when its flow is
ready, after required upstream commits; capturing every internal table's frontier
before upstream work can exclude the newly produced data. Persist those choices
for replay. Input row/byte budgets alone do not bound join expansion, skew or
retained state; use Sail's resource, spilling and cancellation machinery.

### 2. One atomic authority for ownership and progress

**Revise the proposed storage protocol before coding it.** Creating an absent
progress filename does not atomically check a lease in another object. A valid
counter-schedule is: A checks epoch 1; B acquires epoch 2; A creates the still-absent
next progress file. Both object operations can succeed while stale progress wins.
The [finite models](evidence/fable-astra-response/models.json) execute this
counterexample and an amended single-head version check. They model the proposed
protocol; they do not exercise a production object store.

Define one authoritative versioned head containing owner/epoch, generation,
status, committed frontier, pending intent and relevant state references.
Acquisition, renewal, reset and progress must all participate in the same CAS
history, or an actually atomic backend transaction. An append-only journal can
implement that history only if every transition competes for the same next slot,
validates its parent, and rejects gaps and forks. A stale listing must cause a
retry against authority, not permission to skip a conflicting slot.

Require and test conditional-write semantics per backend. Local hard-link-based
Create support is not proof of cloud behavior or power-loss durability; filesystem
persistence and directory durability need their own evidence. Unsupported stores
must fail explicitly. Lease expiry is a scheduling signal, not a guarantee that
an old physical sink commit can no longer succeed.

### 3. Separate replay identity, sink fencing and reset

Use distinct identities for pipeline, flow, physical source/table incarnation,
generation, batch and writer epoch. An application ID containing generation is
useful for deduplication but cannot by itself fence a late old-generation write:
a sink may legitimately accept both distinct application IDs after truncation.

A reset needs a recoverable transition: fence or quiesce old attempts at the sink,
resolve uncertain commits, coordinate target/auxiliary/schema changes, then
activate the new generation. Process cancellation alone is insufficient. A sink
must demonstrate conditional commit/fencing against the expected physical table
identity and generation/epoch, or the runner must reject the unsupported recovery
or concurrent-writer configuration. Do not promise safe automatic takeover from
lease CAS alone.

Store a stable pipeline identity at the control root. Canonical URI spelling
alone does not handle aliases or collisions: encode qualified identities without
ambiguous slash/dot concatenation, record physical table/source IDs, and exclude
credentials from persisted fingerprints. Version a canonical semantic definition
fingerprint; debug output from a resolved plan can contain unstable IDs.
Pending replay must retain its original definition, evaluation context and source
snapshots even when future batches are permitted to use an evolved definition.

Offset arithmetic belongs to each source. Specify opaque cursors and
`plan_range(start, frontier, budget)`, rather than generic numeric addition.
Iceberg snapshot IDs are not ordered counters. Table branches, removals and
rewrites need explicit policies; file sources need immutable manifests/object
versions rather than a directory URI treated as an incarnation. These are adapter
contracts, while durable intent and progress semantics belong in Sail.

### 4. Confirm the original intent and every required effect

**Strengthen the completion handshake.** A highest committed batch number can
prove a prefix only under matching identity, preserved original intent and
contiguous commits. Suppose sink batch 1 wrote range `[0,10)`, while a restored
control store loses that intent. Reconstructing batch 1 as `[0,20)` and accepting
the existing transaction would acknowledge ten unwritten records. Even exactly
one batch ahead is unsafe without the original intent.

A lookup should return a verifiable receipt containing physical sink identity,
generation/batch, effect kind, intent digest and commit version, or an equivalent
provable provider contract. Missing intent, expired transaction metadata, an
unknown outcome or a mismatched identity requires reconciliation or an explicit
failure; it is not permission to invent a replacement range.

Progress advances only after **all** required durable effects are confirmed:
data, operator state and, for CDC, both auxiliary and target updates. Preserve
Sail's existing Delta/Iceberg physical commit operators. Orchestration supplies
intent identity and confirms outcomes; it should not grow another data-commit
engine alongside them.

### 5. CDC needs target-wide coordination and multi-effect recovery

**Keep the two-MERGE strategy, strengthen its preconditions.** Fable's reading of
the SCD1 sequence/tombstone rules is useful. Idempotent replay can avoid a global
two-table transaction under a properly serialized, fenced writer protocol, but
per-flow leases do not establish that protocol for a shared target.

Here is a counter-schedule under an explicitly frozen reconciled-source premise:
A reconciles upsert sequence 10 against an empty auxiliary table; B completes
delete sequence 20, leaving auxiliary sequence 20 and no target row; A's auxiliary
MERGE cannot lower 20, but A's target MERGE can insert its previously reconciled
10 into the absent target. The auxiliary and target now disagree. This is a
counterexample to the draft's sufficient conditions, **not an observed Spark or
Sail runtime defect**; the model records the frozen-source premise.

Coordinate CDC writers by physical target identity plus its auxiliary state,
across flows, pipelines and control roots. The protected interval includes
reconciliation, both MERGEs and schema/reset transitions. Alternatively, prove an
equivalent serializable revalidation protocol. If provider fencing cannot support
that contract, reject overlapping writers explicitly while retaining sequential
shared-target behavior. Catalog aliases must resolve to the same coordination
identity. State assumptions about other writers that do not participate.

The pinned Spark `AutoCdcScd1MultiPipelineSuite` same-target scenario executes one
pipeline and checks it before running the next. It establishes sequential sharing,
not arbitrary overlap safety. Add a controlled interleaving test independently.
Record receipts separately for auxiliary and target effects: the same transaction
identifier on two tables does not turn them into one transaction. Auxiliary-only
success must recover the remaining target effect before checkpoint advancement.
Pin the reconciliation input and evaluation context before either effect so
retries cannot choose a different tied/nondeterministic winner midway through.

### 6. Reuse existing Sail aggregates and Delta conflict tracking

**Correct the `max_by` premise.** Sail already registers `MaxByFunction` in
`crates/sail-plan/src/function/aggregate.rs`; its implementation lives in
`crates/sail-function/src/aggregate/max_min_by.rs`. This was present at Fable's
pinned Sail baseline as well as the current one. Whether DataFusion has an
identically named native aggregate does not decide Sail's capability.
Three unchanged SQL checks for struct values, mixed null ordering and all-null
ordering pass on both [Spark](evidence/fable-astra-response/spark.json) and
[Sail](evidence/fable-astra-response/sail.json). Reuse and extend that implementation
before proposing another aggregate. These checks do not qualify composite CDC
sequence ordering, distributed state merging or every tie/null case.

Likewise, the pinned Delta dependency's `TransactionInfo::new/try_new` derives
`read_app_ids` from `Txn` actions, and the conflict checker examines overlapping
winning application IDs. Do not add a parallel read-set API on the assumption it
is absent. Wire transaction annotations and lookup through the actual write and
MERGE paths, then test duplicate submission, races, retries and reset fencing.
Source inspection of conflict checking is not a successful concurrent-write test.

### 7. Iggy remains a required integration with explicit replay guarantees

Adopt the durable control cursor as the restart authority; disable pre-delivery
or automatic source acknowledgements. Pinned Iggy source documents uncertain
operations, replay-history loss, backup offset lag and ownership changes. Retain
the source's received-message position/context for acknowledgements, including
partition incarnation and consumer-group ownership. Fail closed on a missing or
noncontiguous expected offset, changed incarnation, exhausted replay history or
an unresolvable uncertain operation. An empty poll is not proof that a requested
range is safely consumed.

Acknowledgements are advisory for choosing the restart cursor, but can influence
retention. Fence stale-generation acknowledgements too; otherwise an old owner
can remove data the new owner still needs. Broker evidence must pin the server,
client and message/consumer-offset durability settings. Request/session dedup is
not proof of arbitrary replay-safe exactly-once sink writes. Keep Iggy output at
its demonstrated delivery guarantee until a durable receipt protocol is proved.
The test-source and table-source sequence helps isolate Spark behavior; it does
not make the user's Iggy deliverable optional.

### 8. Dependency boundaries and reviewable delivery

Adopt a small pure control-model module without Arrow, DataFusion, Iggy or a
catalog client dependency. Preserve Sail's session, resolver, catalog and job
boundaries. General catalog support belongs in Sail, with LakeCat as one adapter.

Do not decide either wholesale import or categorical no-reuse before checking
contracts. Audit Grust graph and LakeCat CAS/replay/outbox primitives for small,
independent reusable pieces. Extract and reimport a piece only when behavior and
dependencies fit both existing users and Sail; leave table-specific records in
LakeCat. A short handwritten model is not automatically a complete ownership and
recovery protocol, and an extraction should not drag a service runtime into Sail.

Use the following implementation sequence, with independently reviewable commits:

1. Finish outstanding batch acceptance and faithful Spark fixture ports. The
   combined catalog/CTE/`STREAM` fixture remains pending; passing individual
   catalog assertions does not establish the whole fixture.
2. Freeze source ranges, capability checks and the stateless/stateful boundary;
   add pure transition rules and executable ownership/restore counterexamples.
3. Implement the atomic authority store and provider fencing contract, with
   takeover, reset and ambiguous-outcome fault tests before claiming recovery.
4. Add Delta intent annotations and receipts through existing commits, then a
   stateless AvailableNow vertical slice using a deterministic test source.
5. Add stateful operators incrementally against exact Spark assertions; then
   table-source range semantics and pinned broker-backed Iggy integration.
6. Add CDC argument/schema/sequence parity using existing aggregates, then the
   two-effect recovery journal and shared-target coordination, followed by the
   remaining SCD1/SCD2 and reset/error cases.

Announce the next design checkpoint before choosing stateful execution, provider
fencing or CDC coordination mechanisms; these remain substantive design choices.
Routine implementation can follow the accepted contracts in smaller commits.
Fable's engineer-day estimate remains an estimate until the first fenced,
crash-tested vertical slice establishes the actual effort.

### Evidence and acceptance boundary

The new package contains three paired aggregate checks, one Spark-only state
experiment, and six finite protocol models. Raw scripts and logs are retained.
It provides no new Sail streaming/CDC, Iggy broker or cloud durability verdict.
The original review's 170 CDC parameter expansions are source inventory, not
executed cases, and are already represented within the canonical 462 static
registrations. Do not add them again. The 97 assertion-audited registrations and
59 partial behavioral ports are unchanged by this response; the last broader Sail
receipt remains 273 selected Python and 67 upstream Python executions.

These amendments make the proposal implementable without weakening Spark's
semantics or Sail's architectural boundaries. They leave the batch-first goal
active and expose the remaining correctness obligations before runtime work.

## Astra Ultra follow-through: corrections and implementation gates

Recorded: 2026-10-29T19:22:34.627419+00:00. This addendum follows a second reading of Fable's
review and the response above. It preserves both verbatim, corrects the scope and
status statements below, and adds four concrete recovery obligations. Source
observations use Sail `8d044db3860b4f55e49543c833246af31e986e2e`, Spark 4.2.1
`617618396087429b5627a86ce933bb0f5d6645cb`, and Iggy
`153fdf466aea94b7bcb90681ee7274f9f76ec00d`. The
[source audit](evidence/fable-astra-follow-through/source-audit.json) records
paths, line spans and blob hashes. This pass ran documentation checks, not new
runtime, broker or crash tests.

### Corrected scope and current implementation

The earlier response's step 6 says "remaining SCD1/SCD2"; that wording is wrong.
The target is **SCD1 plus faithful SCD2 rejection**, not an SCD2 implementation.
Spark's `graph/FlowPlanner.scala:98–102` raises
`AUTOCDC_SCD2_NOT_SUPPORTED`; `python/pyspark/pipelines/api.py:539,584,655–663`
restricts the public argument to 1/"1". Preserve both boundaries and their tests.

The combined catalog/CTE fixture marked pending above is now covered at Sail
`8d044db38`: both original SQL files and all five output assertions pass for
memory/memory and memory/LakeCat profiles. Its
[receipt](evidence/8d044db3860b4f55e49543c833246af31e986e2e/gate.json) records
41 Connect Rust tests, 277 selected Python tests and 67 upstream Python executions.
These are selected gates, not full SDP qualification. The canonical inventory
remains 462 registrations, 97 assertion-audited and 59 partial behavioral ports.

[ORC dependency hardening](evidence/orc-dependency-hardening/provenance.json)
has three local commits; it does not yet provide a Sail ORC source or writer.
The [ORC design](ORC-SOURCE-DESIGN.md) retains the metadata budget/type-tree and
portable dependency prerequisites. Streaming/Iggy runtime and CDC execution
remain unimplemented. General catalog behavior stays in Sail; LakeCat remains
one supported adapter.

### 1. A successful no-op still needs a durable completion result

**Source observation.** Sail's `DeltaCommitExec` returns a zero count before
building a commit when it receives no action rows, or no commit payload actions
(`physical_plan/commit_exec.rs:653–680`). Application transactions are appended
later in `CommitData` (`transaction/mod.rs:658–660`). Wiring an annotation only
into that later builder would miss the earlier exits. This is a prerequisite
for the proposed streaming writer, not a demonstrated defect in ordinary batch
writes.

A filtered microbatch can consume input and emit nothing; a CDC auxiliary or
target MERGE can legitimately change no rows. Recovery must distinguish each
completed effect from one that never ran. For an annotated Delta operation,
carry its transaction identity to the commit operator independently of data
actions, and support a transaction-only completion commit when necessary.
An alternative no-op certificate must be durable and bound to the same intent,
table incarnation and conditional validation; a returned row count is insufficient.
Keep ordinary unannotated empty-write behavior unchanged.

Add separate acceptance cases for filtered-empty append, unchanged auxiliary
MERGE, absent-key delete and fully suppressed stale CDC input. Lose the response
after completion, restart, and confirm the original intent exactly once without
requiring an Add/Remove action. If operator state changes despite zero output,
its receipt remains required too.

### 2. Iggy's frontier must name committed, readable input

**Source observation.** Pinned Iggy distinguishes `offset_frontier()` (one past
the highest committed offset, zero before any commit) from `mint_frontier()`
(which can include uncommitted allocations and crash-reservation gaps), in
`core/partitions/src/iggy_partition.rs:3212–3260`. Public `Partition` details
expose `current_offset`, `messages_count` and context, without the internal
committed-seeded flag (`core/common/src/types/partition/mod.rs:24–52`).

Before implementing `frontier()`, specify and test the exact public broker
operation that supplies a committed frontier tied to the partition incarnation.
Do not assume `current_offset + 1` distinguishes a new empty partition from a
first message at offset zero, or that an allocation frontier proves readability.
If the pinned public API cannot establish that distinction, the adapter needs a
small broker/SDK capability extension or an explicitly unsupported case.

Broker tests must cover empty, first-offset-zero, retained-empty, concurrent
append and crash-reservation states. Persist the captured bound for the run;
later arrivals must not extend it. A gap or unreadable promised range remains an
explicit error, with no progress or acknowledgment past it. This refines the
existing fail-closed rule; it does not claim a broker defect from source inspection.

### 3. Preserve auxiliary recreation parity at completed-run boundaries

**Source observation.** Spark's `graph/FlowExecution.scala:404–438` recreates a
missing auxiliary table. `AutoCdcScd1AuxiliaryTableDurabilitySuite.scala:184–220`
requires this between completed runs with the same stream/checkpoint. That
fixture contains only upserts; it proves no restoration of deleted tombstones.

Reconcile this with the earlier physical-identity requirement explicitly:

- With the prior run fully completed and no unresolved effects for the target,
  preserve Spark's recreation behavior. Record the new auxiliary incarnation
  before the next intent; retain the history of the old incarnation.
- If a pending intent names the missing auxiliary incarnation, recreation does
  not prove its effect completed. Stop for reconciliation or reset; do not accept
  a receipt from a replacement table merely because its qualified name matches.
- Dropping auxiliary state destroys its tombstones. Transparent recreation is
  compatibility with that destructive action, not lossless recovery. Add a
  separate delete/late-upsert test so this boundary cannot be misreported.

Apply the check under the target-wide coordination contract, including other
pipelines' unfinished effects. A flow-local idle flag alone is insufficient.

### 4. Cancellation is not proof that a sink did not commit

The existing instruction to stop progress/acknowledgment on cancellation must
retain the pending intent and any confirmed effect receipts. Cancellation can
race a submitted remote commit; dropping the job stream does not establish
rollback. Stop new work and acknowledgments, then let the next valid owner
resolve the original intent through sink lookup. Never reuse its batch identity
for a different range or reset by deleting the unresolved record.

Test both orders: cancellation before the commit is accepted, and cancellation
after acceptance with the response lost. For CDC, inject the same race separately
at auxiliary and target commits. These are required recovery tests, not claims
that such a runner currently exists.

### Concrete handoff to implementation

The design is feasible, but the current documents are not yet a complete
streaming/CDC implementation specification. Treat the following as review gates;
each implementation row should become multiple small commits where needed.

| Boundary | What must be settled or demonstrated before advancing |
| --- | --- |
| Batch completion | Preserve original Spark assertions, finish outstanding batch work and keep provider-specific failures visible. The ORC dependency work is a prerequisite, not an SDP pass. |
| Next Astra design checkpoint | Select the atomic ownership/progress mechanism, prove actual sink fencing and reset behavior, define the stateless/stateful admission boundary, and specify source frontiers and receipt retention. Announce this checkpoint before starting it. |
| Sol: control and Delta vertical slice | Implement the agreed pure transitions, one store adapter and write annotations/codec separately; then one stateless test-source flow. Gate original-intent recovery, no-op receipts, takeover, cancel and reset before adding another provider. |
| Stateful and table-source design | Set operator identity/state recovery, output modes and watermark rules, plus table incarnation/version/branch semantics. Bounded batch execution alone cannot close these items. |
| Sol: Iggy integration | Port the optional dependency and codecs; prove committed frontier capture, explicit range replay, gap rejection and post-progress acknowledgment with pinned broker durability settings. Iggy remains a required deliverable. |
| CDC Astra checkpoint, then Sol | Freeze target-wide coordination, prepared-input replay and two-effect receipts; preserve auxiliary recreation and SCD1/SCD2-rejection parity. Implement arguments, plans, MERGEs, lifecycle and fault tests as separate review units. |

Sail's existing physical operators continue to own data commits; the run actor
owns intent/progress/acknowledgment and uses `JobService`. Audit Grust/LakeCat
reuse by concrete module contracts, keeping the imported dependency surface small.
Fable's day estimates remain provisional until the first recovery-tested vertical
slice; they omit work if stateful streaming is treated as ordinary batch queries.
No new runtime capability or full-goal completion follows from this review.

## Astra Ultra response: remaining corrections and implementation readiness

Recorded: 2026-10-29T20:04:42.822268+00:00. This response follows a fresh reading of Fable's full
review and both Astra addenda. All preceding text is preserved. Source checks use
Sail `4c5d5861d8ba888563d4610d7ab7929fb21fed39`, Spark **4.2.1**
`617618396087429b5627a86ce933bb0f5d6645cb`, and Iggy
`153fdf466aea94b7bcb90681ee7274f9f76ec00d`. The
[source audit](evidence/fable-astra-readiness/source-audit.json) records exact
blobs and excerpts. These are source observations and proposed acceptance gates;
no new runtime, broker or crash tests were run for this response.

**Response to Fable:** the architecture is feasible and worth pursuing. Keep the
existing Sail planner, execution services, catalogs and physical commit operators.
Accept the earlier amendments on stateful semantics, one ownership/progress
authority, sink fencing, reset, no-op receipts and shared-target CDC coordination.
The remaining work is substantial engineering. The review is sufficient to guide
the next design checkpoint, but it is not yet a complete streaming/CDC build
specification. The corrections below make that distinction actionable.

### 1. Iggy needs retention protection before its first acknowledgment

Fable §5.8 says an SDP consumer that never acknowledges pins retention forever.
That is too broad. At the pinned Iggy revision, a poll with automatic commits
disabled does not allocate a stored offset (`message_client.rs:42–45`).
`min_committed_offset` explicitly returns no deletion barrier when nothing has
been committed; external groups do not hold retention
(`iggy_partition.rs:11929–11949`). The removal guard applies only when a stored
barrier exists (`12020–12035`). A new consumer can therefore lose required input
to time or size retention while its first sink effect is still pending.

**Improvement:** specify retention admission separately from restart authority.
The control cursor remains authoritative, but the source adapter must establish
the supported replay lifetime before accepting work. Choose and qualify broker
retention protection or a durable input archive; otherwise expose the bounded
recovery guarantee and stop when input is unavailable. Never fabricate a consumed
offset to create a barrier: starting at zero has no valid last-consumed predecessor.
Deleting an offset removes its barrier; the pinned deletion API lacks a caller
partition context. Reset-time deletion therefore needs its own protected lifecycle,
including recreation between attempts, rather than blind retry.

Also qualify the meaning of a gap. Weaker-durability solo partitions can reserve
offsets before appending, and recovery supports reservation-covered segment gaps
(`iggy_partition.rs:2817–2852,12150–12161`). A gap proves that dense replay is
unverified; it does not by itself prove retention deleted a committed record.
Keep the fail-closed scan rule. Supporting holes requires affirmative broker
evidence about the skipped range, not an assumption that every integer below the
committed upper frontier once contained a record.

**Acceptance:** expire and size-trim input before the first completed effect;
compare absent and established barriers; remove the last barrier during reset;
recreate a partition between delete attempts; crash after a solo reservation and
before append. Check progress and acknowledgments as well as returned rows.
Qualify Persisted topics separately from the weaker durability configuration.

### 2. Delta receipt retention must follow Sail's actual checkpoint behavior

Fable §5.4's guard against `delta.setTransactionRetentionDuration` does not cover
the committed Sail implementation. `sail-delta-lake/src/checkpoint/mod.rs:72–85`
derives transaction expiry from **`delta.logRetentionDuration`**, and `183–194`
prunes transactions with older `last_updated` values. Transactions without that
timestamp survive this particular filter. The existing test at `2974–3009`
explicitly removes an expired application transaction. Log cleanup can then
remove older history; `transaction_version` only returns the retained marker.
This is a source finding, not a new failed recovery experiment.

**Improvement:** use a lookup result with distinct meanings: a matching confirmed
receipt, absence established within sufficiently retained history, or an unknown
outcome because evidence is unavailable. An identity/digest mismatch is a hard
error. A missing marker after expiry must never authorize replay. Any retry also
needs the original intent and conditional sink commit; lookup alone does not
exclude a late in-flight commit.

Select how unresolved intents preserve their evidence, and define the supported
restore horizon across data, receipts and control state. Do not treat omission of
a timestamp as a complete recovery protocol. If the shared Delta retention
semantics need correction, make that a separately reviewed Sail Delta change,
with ordinary table behavior covered as well as SDP.

**Acceptance:** lose the response to a committed effect, checkpoint, clean logs,
restart and resolve the original intent. Repeat after a retention-property change
and with a deliberately expired marker. Unknown outcomes must stop without
duplicating data or acknowledging additional input.

### 3. Iceberg Q5 needs implementation through the real commit path

The apparent snapshot-property setter is insufficient evidence of support.
`sail-iceberg/src/operations/append.rs:79–81` stores properties, but its commit
method at `112–129` does not forward them to `SnapshotProducer`. The physical
writer constructs that producer directly (`physical_plan/commit/commit_exec.rs`,
lines 1218–1231), and the producer builds its own summary. Custom SDP receipts are
therefore still an implementation prerequisite, not an already available option.

**Improvement:** qualify propagation from the write annotation and worker codec
through snapshot construction to an authoritative catalog reload. Cover append,
row-level operations, table bootstrap and annotated no-op completion separately.
Preserve the intent's original lookup/fencing precondition when commit retries
reload newer metadata; changing it to the refreshed parent silently changes the
condition being enforced.

**Acceptance:** confirm the receipt after a lost response and an unrelated later
commit, then exercise snapshot expiration. Absence from the latest snapshot's
summary is not proof of noncommit. Neither is a metadata file that was written
but never published through the catalog. Test the general Sail contract first,
then LakeCat's preservation and conditional publication as one provider.

### 4. Separate CDC key drift from sequence evolution, and seal prepared input

Fable §5.1 assigns `AUTOCDC_INVALID_STATE.KEY_SCHEMA_DRIFT` to a changed key or
sequencing type. Spark's check in `graph/FlowExecution.scala:513–570` compares
the declared **keys** with the recorded key names and types. It does not compare
the sequencing type unless that change also changes a declared key. Sequence
types participate in the CDC metadata/output schema through a different path.
Do not synthesize a key-drift error for every sequence-only change. Port separate
reference cases and preserve their actual error, parameters and failure stage.

The earlier requirement to pin reconciliation input also needs a concrete
mechanism before implementation. Spark's `Scd1ForeachBatchHandler.scala:47–70`
passes one reconciled DataFrame to both MERGEs; this path calls neither `persist`
nor a durable preparation API. Even an in-process cache would not establish
restart-durable prepared rows.

**Recommended next-design choice:** publish an immutable reconciled-batch manifest
and bind its content/schema digest to the pending intent before either MERGE.
Both effects then use that same prepared input. An alternative is a demonstrated
deterministic reconstruction contract covering source and auxiliary snapshots,
evaluation context and tie selection. Choose between these explicitly, including
cost, retention and missing-data behavior; do not leave "pin the input" as an
unimplemented promise.

Target-wide coordination must also expose unfinished work across flow identities
and control roots. A new owner cannot simply begin its own batch after another
flow committed only the auxiliary effect. It must reconcile the prior target's
pending intent first, or reject the takeover. This is a requirement for the
chosen coordination mechanism, not a claim that per-flow state already provides it.

**Acceptance:** crash after preparation and after the auxiliary commit; discard
all process caches; use tied and nondeterministic input; remove or corrupt prepared
data; attempt takeover from a different pipeline. Both effects must use the
original prepared rows, or recovery must stop without advancing progress.

### 5. Design disposition and handoff

| Area | Disposition after this review |
| --- | --- |
| Sail architecture and dependencies | Retain existing services and commit operators. Keep the pure control model small; extract Grust/LakeCat pieces only when their contracts and dependencies fit. General catalog behavior stays in Sail. |
| Batch | Continue the existing implementation sequence and original-assertion acceptance work. ORC is still a prerequisite under construction. |
| Streaming design | Open: atomic authority backend, sink fencing/reset, receipt retention, exact query admission and state recovery. Announce this Astra checkpoint before implementation. |
| Iggy | Required integration. Frontier discovery, retention bootstrap, gap evidence and reset-time offset lifecycle need pinned broker tests before durability claims. |
| CDC | SCD1 plus faithful SCD2 rejection. Sequence/key validation, durable preparation, target-wide pending-work ownership and two-effect recovery remain explicit design gates. |
| Sol handoff | Suitable for settled batch units now. Streaming/CDC implementation needs the named choices and counter-schedule tests first; each provider, codec, transition model and runtime slice remains separately reviewable. |

Fable's S1–S10 and C0–C6 rows sum to **62–94 engineer-days** under their stated
assumptions. That is a planning estimate, not a measured schedule; it excludes
remaining batch work, S0, optional Iggy output and additional stateful/recovery
work exposed by these responses. Re-estimate after the first recovery-tested
Delta vertical slice. The project is realistic, but calling the remaining work
a small connector port would understate it.

At this response's Sail pin, the bounded ORC dependency has been vendored; the
uncommitted schema/reader drafts are not included in a passing verdict. Streaming,
Iggy integration and CDC runtime remain unimplemented in the SDP branch. The last
selected runtime receipt remains 277 Sail Python and 67 upstream Python executions;
the canonical 462 registrations, 97 assertion reviews and 59 partial ports are
unchanged. This append changes review guidance, not the acceptance denominator.

## Astra Ultra review closeout: recovery boundaries and build handoff

Recorded: 2026-10-29T20:49:43.516502+00:00. I read Fable's full review and all three preceding
Astra responses. This addendum preserves them and supplies three further
clarifications, rather than treating previously identified risks as new findings.
Source checks use Sail `4f7a642b710cd377babaae64f26107be805f2c05`, Spark **4.2.1**
`617618396087429b5627a86ce933bb0f5d6645cb`, and Iggy
`153fdf466aea94b7bcb90681ee7274f9f76ec00d`. The
[source audit](evidence/fable-astra-closeout/source-audit.json) retains exact
blobs and excerpts. This response adds no runtime qualification.

**Response to Fable:** retain the overall architecture and incremental delivery
plan. Sail's resolver, catalog abstractions, JobService and physical commit
operators are the right foundation. The streaming and CDC proposals are feasible,
but their recovery mechanisms still need the named design decisions and executed
fault tests. The earlier corrections stand; this review does not approve the
original separate lease/progress files, generation-only fencing or state-free
interpretation of AvailableNow. The remaining work is substantial and should
stay split into small review units.

### 1. CDC preparation must retain the meaning of validation

**Observed in the reference source.** Spark validates the original microbatch
before reconciliation (`autocdc/Scd1ForeachBatchHandler.scala:39–56`). The validator
counts nulls across every input row; deduplication happens afterward. In
`Scd1ForeachBatchHandlerSuite.scala:113–143`, two rows have the same null key and
different sequences. The required error contains ``nullKeyCounts = `id`=2``,
and both tables remain unchanged. Validating only the deduplicated rows would
lose an invalid row and change that count. Lines 207–231 separately require the
null-sequence error to precede the null-key error.

**Improvement to the proposed prepared-input contract:** a manifest of reconciled
survivors is insufficient evidence that the original batch passed validation.
Bind successful validation and prepared rows to the same input/evaluation
identity before publishing a state that permits either MERGE. Preserve the
order: validate all input rows, deduplicate, derive metadata, apply selection,
apply tombstones, then seal the prepared result. An empty result still needs the
validation result and the previously specified no-op completion receipts.

Durably staging the evaluated input is one implementation; deterministic
reconstruction with equivalent guarantees is another. This is a recommended
Sail recovery property, not a claim that Spark's lazy DataFrame path proves it.
The next CDC design must choose the mechanism without silently changing Spark's
expression evaluation or error precedence.

**Acceptance:** port the existing duplicate-null-key, composite-key count and
error-precedence assertions unchanged. Add a null-sequence row that would lose
deduplication to a valid row with the same key. Crash between validation and
preparation, discard process caches, and verify that recovery cannot certify a
different input or bypass validation. No auxiliary/target effect may occur for
an invalid batch.

### 2. Distinguish inferred CDC metadata from an existing target's contents

**Coverage correction.** The metadata-auto-add case in
`graph/AutoCdcScd1TargetTableDurabilitySuite.scala:119–157` starts with an empty
target. Its preloaded-row cases explicitly supply CDC sequence metadata. They
do not establish behavior for a populated target whose old rows have no stored
CDC version. The target MERGE uses ordinary `>` and `>=` comparisons against
the stored upsert sequence (`Scd1BatchProcessor.scala:347–365`); it supplies no
default version for null metadata. SQL null comparison semantics therefore
suggest neither matched action wins in that situation, but that is a source
inference requiring a reference execution, not a reported test result.

**Improvement:** keep three separate reference cases: empty target without the
metadata column, populated target without it, and populated target with null
metadata. Preserve observed Spark behavior and errors; do not invent a zero or
minimum starting sequence. Also preserve Sail's existing distinction between
flow schema and materialized table schema: Spark applies `asNullable` to inferred
table schemas (`graph/DatasetManager.scala:262–264`), and Sail already applies
`nullable_fields` in `pipelines/schema.rs:94–101`. The non-null metadata field
described in Fable §6.1 is not a blanket physical-table nullability requirement.

### 3. Iggy acknowledgment uncertainty is separate from missing input

**Qualification of the first Astra response's broad fail-closed wording.**
Iggy's `OperationNotRetained` means this client can no longer resolve a request's
outcome after reset, abandonment or outcome eviction
(`core/common/src/traits/client.rs:85–106`). It does not establish that source
messages disappeared. `OperationUncertain` may follow a committed offset store;
`LaneBlocked` means the requested store was not sent
(`core/sdk/src/clients/consumer.rs:794–814`).

Use phase-specific recovery rules:

| Condition | Required treatment |
| --- | --- |
| A pending batch cannot replay its promised input | Stop without advancing data progress or acknowledging the missing range. |
| All required effects and durable progress are confirmed, but acknowledgment is uncertain | Keep the batch committed and record acknowledgment as pending. Never rerun its data effects, roll back progress or replace its intent merely to retry acknowledgment. |
| Retained request resolution becomes unavailable | Preserve the unknown acknowledgment outcome. A new acknowledgment attempt requires the protected lifecycle and a position justified by durable progress; expiry alone permits no data replay. |
| The captured partition incarnation or owner is refused | Report the refusal and preserve the committed batch. Never substitute a replacement context to force acknowledgment through. |

Persist the **complete acknowledgment identity**. `ConsumerPosition` contains
partition, inclusive offset and context, while consumer, stream and topic are
supplied separately (`consumer_offset_info.rs:36–45`; `consumer.rs:288–295`). A
saved position must not be attached to whichever consumer happens to exist after
restart. Scalar offset retries can acquire a replacement context; captured-position
retries retain the original one (`consumer_offset_client.rs:27–39`).

Whether an acknowledgment backlog pauses later batch admission is a retention
and operational policy to select explicitly. It does not change an already
confirmed data outcome. This preserves the earlier retention-bootstrap and
stale-generation acknowledgment requirements.

**Acceptance:** commit data and progress, lose the acknowledgment response, then
reset the SDK session so request resolution is unavailable. Restart and verify
no repeated range execution or sink effect. Repeat after partition recreation
and ownership change; replacement progress must remain untouched. These are
proposed broker tests, not an assertion that the current adapter passes them.

### Handoff decision

The next streaming design checkpoint should produce one worked recovery trace
for the chosen store and Delta sink: original intent, ownership takeover,
conditional data/no-op receipt, progress, acknowledgment, and reset. Name the
actual atomic operations and retained evidence at every step. Include the
missing/expired receipt case. That concrete trace, plus the admitted query
subset, is the entry condition for Sol's separately reviewed control-model,
store, writer/codec and run-actor commits. Announce that design phase before
starting it. Stateful execution, table-source frontiers and CDC coordination
retain their own announced design checkpoints.

At the current Sail pin, the separately gated TIME metadata, immutable ORC
range reader and native timestamp-precision vendor units are recorded in the
[foundation evidence](evidence/orc-sail-foundation/provenance.json) and
[precision evidence](evidence/orc-timestamp-precision/provenance.json). They do
not qualify an integrated Sail ORC source/writer. Existing uncommitted TIME/ORC
drafts are outside this review verdict. Streaming/Iggy and CDC runtime remain
unimplemented; the selected public runtime receipt remains 277 Sail Python and
67 upstream Python executions. The canonical inventory is unchanged. Sol can
continue settled batch units; the remaining streaming/CDC choices are still
design work. Fable's revised 62–94 engineer-day subtotal remains provisional,
with the exclusions already recorded above.
