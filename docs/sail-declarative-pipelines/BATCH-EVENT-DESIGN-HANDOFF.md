# Next design checkpoint: batch failures and events

The operator requests notice before a new design phase so they can switch from
Sol to Astra. That boundary has now been reached for batch failure attribution
and event delivery. This note records evidence and open decisions; it does not
choose a new architecture. Streaming checkpoint/recovery and CDC remain later
design phases.

Baseline Sail is `5a5e256328406b6dcbffd0db83dd39d6f9746553`; its detached gate
passed 112 selected Sail cases and 67 upstream Python executions. The Spark
reference remains `617618396087429b5627a86ce933bb0f5d6645cb`.

## Evidence motivating the checkpoint

Spark `ViewSuite.scala:221` registers `pv1 AS SELECT 1 + 1` and `pv2 AS SELECT *
FROM pv1`. It asserts an ERROR/FAILED event for pv1 containing
`CREATE_PERMANENT_VIEW_WITHOUT_ALIAS`, and an INFO/SKIPPED event for pv2.
`DatasetManager.materializeViews` catches publication failures per view, tracks
failed dependencies, skips affected views, and continues independent publication.

Sail `pipelines/materialize.rs::views` currently returns on its first catalog
error. `pipelines/analysis.rs::analyze` also returns immediately on a direct
resolution failure. `pipelines/mod.rs` emits only starting/completed messages and
uses `outcome?` to propagate errors through the existing executor. There is no
per-flow failure/event model in these modules. A focused baseline probe of the
upstream failed-view SQL is retained under
[evidence](evidence/batch-event-design-boundary/baseline.json).

Spark's internal `PipelineEvent` includes origin, severity, flow/run details,
and an optional error. Connect `PipelineEventSender.constructProtoEvent` sends
only timestamp and `messageWithError` in the current wire message. Therefore,
Connect text assertions alone cannot verify the Scala suite's internal status
and severity assertions. Internal and wire evidence must be distinguished.
Spark's sender always enqueues run-progress and terminal flow-progress events;
nonterminal events may be dropped when its configured queue is full.

## Decisions for the focused design review

- Define the internal flow/run outcomes needed for direct errors, blocked
  dependencies, publication failure, independent success, cancellation, and
  terminal completion. Identify which assertions belong to internal tests and
  which can be observed through Spark Connect.
- Decide how analysis reports multiple direct and downstream failures while
  retaining the required outer exception behavior and structured causes.
- Decide how execution emits progress through Sail's existing Executor response
  buffering, cancellation, reattachment, and completion handling. Specify
  backpressure and terminal-event delivery without introducing a second query
  scheduler or holding registration locks across asynchronous work.
- Preserve Spark's distinct behavior for table materialization errors, individual
  view publication failures, and query execution failures. Establish ordering and
  terminal-run semantics from source and live references before implementing them.
- Identify the shared permanent-view alias validation change independently from
  pipeline failure propagation. Preserve Sail's typed AST/spec/planner path.
- Define granular implementation units and the corresponding upstream assertion
  ports, including failure injection and cancellation coverage. Keep JobService
  execution and existing distributed-plan codec requirements intact.

Use the view crosswalk first, then GraphExecution, TriggeredGraphExecution,
ConstructPipelineEvent, FlowProgressEventLogger, PipelineEventSender and stream
suites to extend the acceptance scope. The full batch goal remains open; this
checkpoint is not a request to begin streaming implementation.

## Catalog follow-up evidence

Sail 24533f1f0d passes four live table materialization/refresh cases against
unchanged LakeCat 27e18f39 through the existing Iceberg REST provider. A shared
Iceberg field-doc conversion fix was required in Sail; LakeCat stored the correct
doc before the fix. Standard persisted-view support remains a separate review
input: Sail rejects existing REST view replacement, and LakeCat lacks standard
POST view-create routes. Preserve the ownership clarification: shared catalog and
Iceberg semantics belong in Sail, with LakeCat providing its protocol adapter,
persistence/CAS and governance. No new view architecture is selected here.

## Failure-handler assertion audit

PipelinesHandlerSuite at the pinned Spark revision has two registration sites.
The cause-present fixture requires exception object identity on rethrow. The
cause-absent fixture uses both UnexpectedRunFailure and FailureStoppingFlow(t1,t2)
messages and requires SparkException condition PIPELINE_RUN_FAILED with the
verbatim message parameter. Both remain unmapped in Sail's assertion inventory.
The eventual outcome/error design must retain these distinctions; no architecture
is chosen here. The source hash and audit limits are recorded in the
[handler audit](evidence/handler-crosswalk/validation.json).

## File-source cause observation

The file-input reference confirms that Spark's outer unresolved-pipeline exception
does not include the empty-location cause. Preceding flow events carry that cause.
The passing wire port collects events and the outer error without requiring one
specific transport location for the cause. Original resolutionFailedFlows objects,
dataset attribution and missing-file instance remain unqualified. Initial wrong-
observer reference failure is retained in the [receipt](evidence/9c42934ed8e095b2e7ccaafeef2faea3f35f797a/gate.json).
The [file-source handoff](FILE-SOURCE-DESIGN-HANDOFF.md) records the separate ORC gap.
