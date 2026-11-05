# StreamSource foundation review

## Scope and evidence

Source baseline: Sail `85c6cca01cd521dd778bc200c987a34edf141de1`, inspected in
`/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01`.
Paths below are relative to that checkout unless explicitly qualified.
The comparison baseline is `62251e0a27bbab0a15547562e829cad2a418f353`.
Dependency behavior was checked in the locally installed source matching
Cargo.lock: DataFusion 55.2.0 and Arrow 59.2.0.

This is source inspection, including existing tests and documentation, not a
runtime-test verdict. No Sail, Spark, broker or Rust suite was executed.
Failure examples below are source-derived predictions unless stated otherwise.
The inventory distinguishes complete streaming modules from selected sections
of larger integration files. It is not a claim that every engine dependency
or every unrelated executor line was audited.

Separate [executed component probes](TEST-EVIDENCE.md) subsequently reproduced
empty-schema decoding failures, decimal marker type mismatches, marker-expression
failures and metadata loss using unchanged pinned source. This source audit
remains source inspection. Those probes do not establish complete SQL-plan,
distributed alignment, fencing or durable-recovery behavior.

The core streaming trait, rewriter, logical and physical nodes, rate/socket
sources and query manager are unchanged from the earlier baseline. The only
diff within those selected paths adds a generated-module lint attribute in
`event/mod.rs`. Broader execution and planning integration has changed.
The new source-reuse exclusion is relevant to safe scan ownership.

## Verdict

Build on StreamSource, ordered flow events, Sail's plan pipeline and existing
job/task execution. These provide a coherent extension point. They do not yet
provide a marker-safe general execution graph, replayable production sources,
durable checkpoints, retractable collection or table-sink recovery.

Foundation correctness must precede plugging durable sinks into ordinary
RecordBatch operators. Adding a coordinator beside the engine would leave
expression evaluation, exchanges, termination and resource behavior unresolved.
The smallest coherent change extends existing execution ownership and makes
its admitted flow operators explicit, with typed capabilities and failure
contracts. It does not add a second bounded-query engine.

## What already exists

| Layer | Observed behavior and reference | Reuse boundary |
| --- | --- | --- |
| Source interface | `sail-common-datafusion/src/streaming/source.rs:15–44` provides data schema, constraints, filter capability and scan returning an encoded flow-event plan | Preserve the interface; add optional recovery capabilities rather than pretending every source can resume |
| Provider bridge | `source.rs:63–94` exposes the ordinary schema, forwards filter capability and refuses direct scan | Reuse logical provider detection and existing source resolution |
| Actual sources | Only rate and socket implement `StreamSource`; `sail-data-source/src/formats/rate/reader.rs:59`, `socket/reader.rs:56` | Both are test sources; neither exposes resume, positions, barriers or durable identity |
| Event model | `event/mod.rs:15–25` carries data plus per-row retraction flags; `event/marker.rs:9–35` defines latency, watermark, checkpoint and end of data | Keep typed events and ordered control; distinguish retraction from ordered business deletion |
| Arrow encoding | `event/encoding.rs:42–76,141–173` stores marker bytes and retraction flags in two leading columns and can split mixed batches back into ordered events | Useful transport representation; not permission to run arbitrary SQL expressions on marker rows |
| Plan pipeline | `sail-plan/src/lib.rs:42–57` optimizes the logical plan, detects streaming, rewrites, then physically plans | Integrate admission and flow-safe operators here rather than another planner |
| Rewriter | `streaming/rewriter.rs:69–184` adapts scans, projections, filters, limits, unions and aliases; refuses windows, aggregates, sorts, joins, repartition and unnest | Existing support is narrow; new shapes require explicit semantics, state and optimizer protection |
| Physical source construction | `sail-session/src/planner.rs:449–461` calls source.scan and handles rename/projection | A source descriptor exists during planning; the live scan exists during execution |
| Execution ownership | `sail-execution/src/job_runner.rs:63–86,114–139` directly executes locally and dispatches through the driver in cluster mode | Do not add a local driver; job-owned recovery can use mode-specific routes |
| Worker construction | `task_runner/actor/handler.rs:57–82`, `task_runner/preparation.rs:59–89` reconstruct a fresh executable plan for each task | Control handles must be task/attempt scoped; a process-local Arc from planning cannot control decoded worker scans |
| Transport | `stream/writer.rs:23–34` preserves per-channel batch order; Flight carries Arrow batches in `stream/service/client.rs:77–92` | Reuse transport, with explicit marker rules at every routing and fan-in boundary |
| User lifecycle | `sail-spark-connect/src/streaming.rs` tracks active/stopped/error state; session starts queries after JobService execution | Reuse query registration and cancellation; enrich durable identity and successful-completion meaning |

All table references in the table above have the common `crates/` prefix.

## High-priority foundation findings

### User expressions execute on marker placeholders

Observed: `sail-plan/src/streaming/rewriter.rs:69–86` inserts control columns
into an ordinary Projection and constructs `user_predicate OR marker_present`.
`StreamFilterExec` calls DataFusion batch_filter on the encoded batch at
`crates/sail-physical-plan/src/streaming/filter.rs:122–129`.
Marker payload columns are null or manufactured values at
`crates/sail-common-datafusion/src/streaming/event/encoding.rs:63–71`.

DataFusion 55.2.0 `physical-expr/src/expressions/binary.rs:534–555` evaluates
the left operand before short-circuiting. The injected predicate therefore
does not protect user evaluation on marker rows. Its projection implementation
`physical-expr/src/projection.rs:952–970` evaluates all requested expressions.

Prediction: a strict cast of a nonnullable string placeholder, a function
rejecting zero/empty input, or an effectful function can fail or execute on a
checkpoint even when every real row is valid. No executable reproducer was run.

Change: flow-aware transform adapters should apply expressions only to data,
forward markers unchanged and preserve retraction flags. Reordering the filter
OR could address one expression path but does not solve projections or general
functions. Retain the Arrow encoding at transport boundaries.

### Distributed fan-in and shuffle are not checkpoint-aware

Observed: `crates/sail-execution/src/stream/merge.rs:21–35` uses select_all;
`stream/accessor.rs:285–340` merges fetched producer streams that way.
`job_graph/planner.rs:592–605` can replace CoalescePartitionsExec with shuffle.
`plan/shuffle_write.rs:274–288` partitions every nonempty RecordBatch without
recognizing markers. Celeborn also merges decoded channels with select_all at
`stream/celeborn/core.rs:149–168`.

Implication: per-channel ordering is insufficient for a consistent checkpoint
across channels. Once repartitioned stateful execution is admitted, control
markers need defined propagation to every downstream participant, not routing
by fabricated payload keys. This is a design blocker for that extension, not
a claim that currently rejected repartition queries silently corrupt data.

Change: define event-aware exchange/fan-in behavior and optimizer admission
alongside the proposed aligned merge. Every physical plan and serialized task
must preserve the same participant set and boundary. A merge inserted only in
a local prototype does not establish that property.

### Completion and retractions are only partly implemented

Observed:

- `crates/sail-physical-plan/src/streaming/collector.rs:122–131` discards every marker and ignores retraction flags, despite its final-result documentation.
- `source_adapter.rs:96–105` emits EndOfData and then closes without waiting for a checkpoint.
- `limit.rs:259–265` closes when fetch is exhausted; its TODO explicitly calls for EndOfData and continued checkpoint propagation.
- `crates/sail-data-source/src/formats/console/writer.rs:99–115` prints input errors and continues, returning no error from that path.
- `crates/sail-spark-connect/src/streaming.rs:70–85` records an error but continues consuming, and stop wins a select that drops the stream.
- `service/plan_executor.rs:354–364` reports no progress and treats ProcessAllAvailable as a no-op.

These facts must not be hidden under “existing completion machinery.” Preserve
the lifecycle framework, but separate end of input, task closure, cancellation,
failed execution and successfully committed final checkpoint. Durable sinks
must stop advancing after failure. Either implement retractable collection or
reject retracting inputs explicitly where semantics are unsupported.

### Bounded channels do not establish bounded streaming memory

Observed: `crates/sail-execution/src/stream/local/memory.rs:63–69,117–127`
uses unbounded overflow queues for slow replicas; its comment identifies a
batch-execution deadlock reason. `stream/storage/core.rs` is a blocking shuffle
backend with attempt-scoped output and cleanup, not an incremental checkpoint
log.

Change: design credit/backpressure or spill with the actual task graph. Do not
replace overflow by a bounded queue without reproducing the motivating
fan-out deadlocks. Byte accounting must include retained replica data,
checkpoint output and operator state. Checkpoint cadence cannot enforce this.

### Recovery identity and controls need execution-level integration

Observed: the source trait has no checkpoint operations; JobRunner has execute,
explain and stop only. TaskRunnerMessage has task lifecycle/stream operations,
not checkpoint control. Rate/socket codec entries serialize options, schema
and projection only, at `crates/sail-execution/src/proto/codec.rs:1319–1366,
2860–2891`. Query and run IDs are both regenerated on every start at
`crates/sail-spark-connect/src/session.rs:273–279`.

Change: retain a stable flow/rebuild identity independently of transient jobs
and attempts. Register source-partition control endpoints when execution
starts, route commands through existing task ownership, and reject stale
attempt responses. A source capability describes replay and position semantics;
a live handle performs serialized commands. Avoid a mutable controller shared
accidentally across independent scans. `crates/sail-data-source/src/reuse.rs:10–23`
now explicitly prevents reusing streaming providers, including renamed wrappers.

## Additional correctness and coverage gaps

The decoder constructs the data batch with `RecordBatch::try_new` after
removing both control columns at `event/encoding.rs:137`. For an empty data
schema this supplies no row count. Arrow 59.2.0 `record_batch.rs:338–344`
rejects that shape. Rate generation similarly constructs zero projected columns
without an explicit count at `rate/reader.rs:329–357`. Add zero-column data and
marker round trips, including literal-only projections. This is a source-level
failure deduction, not an executed SQL failure.

`crates/sail-common-datafusion/src/array/placeholder.rs:338–341` discards decimal
precision and scale, using the generic primitive builder at `:395–401`.
Arrow validates the resulting column type against the field at
`record_batch.rs:365–385`. A nonnullable nondefault decimal marker is therefore
predicted to fail encoding. Existing placeholder tests check length and null
count at `placeholder.rs:426–436`, not exact datatype. Extend coverage to exact
type, schema metadata and nested types. Encoding schema helpers currently
rebuild `Schema::new` rather than preserving schema metadata at
`event/schema.rs:37–47,68–80`. Reserved `_marker`/`_retracted` name collisions
also need explicit admission or unambiguous field addressing.

`StreamSourceWrapperNode` equality/hash exclude the source object at
`crates/sail-logical-plan/src/streaming/source_wrapper.rs:29–47`. No harmful
common-subplan reuse was demonstrated, and rewriting follows logical
optimization. Nevertheless, future optimizer reuse must key on real source
identity, not just schema/filter equality. Preserve the newer provider reuse
exclusion rather than treating equivalent-looking streams as interchangeable.

Rate partitions each start values at zero and timestamps use wall time at
`rate/reader.rs:321–349`. A row counter is a protocol test position, not
repeatable production input. Socket explicitly has no reconnect/retry and is
for testing at `socket/reader.rs:207–209`. Neither is evidence for exactly-once
recovery. PythonDataSourceStream is ordinary RecordBatch iteration, not an
additional StreamSource implementation.

WriteStream conversion ignores trigger and output_mode at
`crates/sail-spark-connect/src/proto/plan.rs:2075–2091`; write resolution forces
append at `crates/sail-plan/src/resolver/command/write_stream.rs:43–53`.
Listing file writes explicitly reject flow schemas at
`crates/sail-data-source/src/listing/planner.rs:212–214`. Do not describe existing
writeStream as durable table streaming. Unsupported requested guarantees should
be refused or translated explicitly, not silently accepted for API resemblance.

## Comparison with prototypes and engineering changes

P4 `4fad33ca5` adds a local coordinator, aligned merge, file sink, file state,
window and whole-batch change reducer. P1/P2 are included in that stack.
Its codec diff only adds Delta application-transaction fields; it does not
serialize the new flow operators or distribute source controls.

The prototype controller asks “emit at your current position,” not “replay
this exact pending boundary” at
`/Users/alexy/src/sail-proto-p4/crates/sail-common-datafusion/src/streaming/checkpoint.rs:28–39,98–104`.
Its rate controller uses a latest-value watch request at
`crates/sail-data-source/src/formats/rate/checkpoint.rs:114–118` relative to that
prototype. The merge separately counts ended and closed inputs at
`crates/sail-physical-plan/src/streaming/merge.rs:135–149`. The state store's
reclamation comment permits removal after a position is recorded at
`state_store.rs:132–149`. These mechanisms remain useful test material, not a
ready protocol. Retain exact pending boundaries, immutable output meaning,
per-effect completion and every needed restart snapshot.

The recommended engineering order is:

1. Make admitted operators marker-safe and define completion/failure states.
2. Prove transport and fan-in preserve markers and backpressure in local and cluster plans.
3. Add task-scoped source participation and stable recovery identity to existing job execution.
4. Implement one durable source-to-target path with commit-time fencing, exact recovery and explicit resource limits.
5. Extend operators and sources only with their own state and replay contracts.

These dependencies do not demand a general coordinator service. Existing job,
task, codec, transport, catalog and storage interfaces should carry the work.
If DataFusion operators need ownership changes, compare a narrow attributed
implementation with adapters; do not accumulate expression-specific workarounds.

Spark parity does not justify undefined, checkpoint-dependent business results.
Specify event identity, ordering, duplicates and conflicting equal-sequence
changes independently of execution scheduling. Consider rejecting ambiguous
conflicts unless an application supplies a tie-breaker. Source transport order
is not automatically business order. All admitted durable writers require
commit-time fencing; an external single-writer convention is not its replacement.

Two-table change capture is a storage choice. An atomic keyed-state table with
order metadata and tombstones can remove a partial two-effect commit, but it
changes ordinary table reads unless the target supports hidden metadata and
logical deletion semantics. An internal state table plus a separate published
table reintroduces two effects. Do not silently replace a table with a view.
Compare target-native atomic state, an explicitly accepted state-table interface,
and separately tracked target/auxiliary effects against actual reader and DDL
requirements before selecting storage.

## Tests that would refute the design

Inject all marker kinds through casts, division and user-defined functions;
assert functions run only on data. Round-trip empty data schemas and all Arrow
types with exact datatype and metadata. Mix marker/data rows and retractions.
Run staggered end/close, overlapping checkpoints and task replacement through
the actual optimized local and cluster plans. Exercise hash and multi-input
fan-in only when their marker rules are implemented. Crash at every durable
effect, then add input and retry. Pause a writer across takeover. Saturate a
slow replica while limiting memory and verify progress without unbounded queues.

The existing source tests exercise rate projection/filter/limit and union with
a bounded source, socket behavior and query lifecycle. Marker tests cover
protobuf round trips. They do not establish these failure properties.

## Inspected-file inventory

The following lists every source file used substantively for this assessment.
Searches also traversed crates, docs and Python tests for all StreamSource,
FlowEvent, marker, streaming and rewrite references. Paths in grouped rows are
all relative to the pinned Sail checkout; comma-separated filenames name
individual files. “Sections” means the relevant integration paths were read,
not an unrelated whole module audit.

| Area | Files inspected | Depth |
| --- | --- | --- |
| Interface and events | `crates/sail-common-datafusion/src/streaming/source.rs`, `mod.rs`; `streaming/event/mod.rs`, `schema.rs`, `encoding.rs`, `marker.rs`, `stream.rs`; `crates/sail-common-datafusion/proto/sail/streaming/marker.proto` | Complete streaming files |
| Arrow placeholders | `crates/sail-common-datafusion/src/array/placeholder.rs` | Construction and test sections |
| Logical nodes | `crates/sail-logical-plan/src/streaming/source_wrapper.rs`, `source_adapter.rs`, `filter.rs`, `limit.rs`, `collector.rs`, `mod.rs` | Complete |
| Physical nodes | `crates/sail-physical-plan/src/streaming/source_adapter.rs`, `filter.rs`, `limit.rs`, `collector.rs`, `mod.rs` | Complete |
| Rewriter | `crates/sail-plan/src/streaming/rewriter.rs`, `mod.rs`; `crates/sail-plan/src/lib.rs` | Complete |
| Rate/socket | `crates/sail-data-source/src/formats/rate/mod.rs`, `options.rs`, `reader.rs`; corresponding three `socket/` files | Complete |
| Source reuse | `crates/sail-data-source/src/reuse.rs` | Complete |
| Python distinction | `crates/sail-data-source/src/formats/python/mod.rs`, `stream.rs` | Exports, source reader, record-batch transport sections |
| Sink interfaces | `crates/sail-data-source/src/formats/console/mod.rs`, `writer.rs`; `formats/noop/mod.rs`, `writer.rs`; `listing/planner.rs` | Complete console/noop; listing write-admission section |
| Planning integration | `crates/sail-session/src/planner.rs`; `crates/sail-plan/src/resolver/command/write_stream.rs`; `resolver/query/misc.rs`, `read.rs` | Streaming planner and resolver sections; complete write_stream |
| Query API | `crates/sail-spark-connect/src/streaming.rs`, `session.rs`, `service/plan_executor.rs`, `proto/plan.rs` | Complete streaming manager; query start/stop/status/await and writeStream conversion sections |
| Job interface | `crates/sail-common-datafusion/src/session/job.rs`; `crates/sail-execution/src/job_runner.rs` | Complete |
| Task execution | `crates/sail-execution/src/task_runner/actor/message.rs`, `core.rs`, `handler.rs`; `task_runner/preparation.rs`; `worker/actor/handler.rs` | Message variants, dispatch, run/stop/status/preparation and worker lifecycle sections |
| Serialization | `crates/sail-execution/src/proto/codec.rs`; `proto/sail/plan/physical.proto` | Streaming source/operator encode/decode and node definitions |
| Distributed planning | `crates/sail-execution/src/job_graph/planner.rs`; `plan/stage_input.rs`, `plan/shuffle_write.rs` | Stage boundary/repartition/coalesce paths; complete stage input; shuffle write path |
| Data transport | `crates/sail-execution/src/stream/merge.rs`, `reader.rs`, `writer.rs`, `accessor.rs`, `local/memory.rs`, `storage/core.rs`, `celeborn/core.rs`, `service/client.rs`, `service/transport/mod.rs` | Complete merge/local-memory/client; relevant reader, writer, fan-in, storage, Celeborn and Flight transport sections |
| Tests | `python/pysail/tests/_dev/spark/streaming/test_streaming_basic.py`; `datasource/test_rate.py`, `test_socket.py` under the same spark directory | Complete; test_basic.py streaming start located by search only |
| Public docs | `docs/concepts/architecture/index.md`, `docs/concepts/query-planning/index.md`; `docs/reference/changelog/index.md`, `docs/guide/dataframe/features.md`, `docs/introduction/migrating-from-spark/index.md` | Complete architecture/planning; streaming status entries in others |
| Exact dependencies | Cargo.lock; local `datafusion-physical-plan-55.2.0/src/projection.rs`, `filter.rs`; `datafusion-physical-expr-55.2.0/src/projection.rs`, `expressions/binary.rs`; `arrow-array-59.2.0/src/record_batch.rs`, `builder/primitive_builder.rs` | Version pins and evaluation/type-check paths |
| Prototype comparison | P4 `streaming/checkpoint.rs`, rate `checkpoint.rs`, physical `streaming/merge.rs`, `state_store.rs`; codec/proto diff against base | Coordinator/controller/merge complete relevant paths, state read/reclaim and entire codec/proto diff; P3 behavior relies on the separately recorded prior review, not a fresh complete reread |

The eight design documents and original prototype/runtime review context were
read in the preceding substantive and editorial passes. This assessment adds
current upstream foundation inspection; it does not relabel previous prototype
runs as new executions. Fencing implementation and typed configuration are
separate complementary review slices, not independently verified here.
