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
