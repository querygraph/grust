# Review: captured Session transfer and analyzer access

Fable's source-pinned review of Codex's draft
`CAPTURE-EXECUTION-TRANSFER-DESIGN.md` (coordinator Grust docs, uncommitted
at review time), requested in CF-0207. Read only: no code, no runtime change,
no Status-rendering choice; the A–D/C5 boundaries and E′ are untouched.

## Pins

| Item                   | Pin                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sail root              | `ece5b6aed15462cbc54f18a6f72482f1f5e2ad51` (`work/spark-declarative-pipelines`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Characterization       | `e42e1be96` (`job_runner/local/capture_boundary_tests.rs`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Analyzer primitive     | `ece5b6aed` (`session/scoped.rs` `ScopedSession::analyze`, `scoped/analyzer_tests.rs`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| DataFusion             | 55.2.0 (`datafusion`, `datafusion-execution`, `datafusion-session`, `datafusion-expr`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Files read at the root | `session/scoped.rs`, `session/job.rs`, `task_resources.rs`, `task_resources_context.rs`, `managed_stream.rs`, `managed_stream/preparation.rs`, `job_runner.rs`, `job_runner/local.rs`, `job_runner/local/preparation.rs`, `driver/job_scheduler/core.rs`, `driver/actor/handler.rs`, `task_runner/actor/handler.rs`, `worker/actor/core.rs`, `proto/codec.rs`, `sail-delta-lake/src/{table/mod.rs, logical/table_source.rs, datasource/scan.rs, physical/table_scan_planner.rs, physical_plan/planner/log_scan.rs}`, `sail-iceberg/src/{datasource/scan.rs, lake_source.rs}` |

Every statement below is from those files; where a claim is not source-checked
it says so.

## Summary

The draft's observations hold at the root: `SessionContext::state()` marks
execution start, the legacy `execute` re-captures authority late, the analyzer
primitive is optimizer-free, and the registry overlay reaches planning but not
legacy execution. The candidate (consuming `capture` on the preparation
returning a captured object with a borrowed `ScopedSession`) is implementable
with pieces that already exist (`ScopedSession::task_ctx` plus
`ScopedTaskContext::from_resources`). Three things need stating before the
interface is accepted:

1. **Capture failure must go through `StreamPreparation::fail`, never `Drop`.**
   Otherwise the primary error is "managed stream preparation abandoned" and
   the typed capture error is lost (§1).
2. **Delta is owner-bound at the source, Iceberg is not.** A Delta logical plan
   carries a `LogStoreRef` built from the _creating_ Session's store and every
   later log, CDF and commit path reads or writes through it, while data files
   are read through the _executing_ Session's store. Reusing an analysis-time
   plan under a later attempt splits one table across two store lineages; for
   commits this is a correctness hazard, not only a lifetime question (§2).
3. **A captured registry never reaches cluster workers.** Workers derive their
   task context from their own `SessionContext`; the driver uses the caller's
   `TaskContext` only for encoding and driver-local storage cleanup. Cluster
   `capture` must be explicit-unsupported until a worker-resolvable form
   exists (§3).

## 1. Captured guard, error and drop transitions; registry without re-capture

**What exists.** `LocalJobPreparation { runner: &LocalJobRunner, id, context:
SessionContext, resources: Arc<TaskResourceScope>, preparation:
StreamPreparation, control }` (`local/preparation.rs`). `execute(self, plan)`
checks `resources.cancelled().now_or_never()` first; on cancellation it calls
`preparation.cancel()`, awaits completion, `runner.reap()` and returns the
report's error. Otherwise, inside `catch_unwind`, it builds
`ScopedTaskContext::from_resources(&context.task_ctx(), resources)` and
`execute_stream`s; on `Err` it calls `preparation.fail(error)`, awaits
`control.completion()`, reaps, and returns the report's error. `StreamPreparation`
has `complete`, `finish`, `cancel`, `fail`, and a `Drop` that, if not finished,
runs `finish_error(Internal("managed stream preparation abandoned"))`
(`managed_stream/preparation.rs`). `TaskResourceScope::Drop` only latches
cancellation ("best effort only"); `register` refuses once sealed with
`Execution("task resource scope is sealed")`; `drain` is shared and joins every
supervisor; cancel/seal are synchronous (`task_resources.rs`).

**Findings.**

- **1.1 Capture failure path.** The draft's check 1 ("obtain control before
  consuming capture if an error otherwise consumes the guard") is necessary and
  the existing `execute` shows the pattern to copy: a fallible step inside a
  consuming method must end in `preparation.fail(error)` followed by
  `control.completion().await` and `runner.reap()`, so the drain report's
  primary is the typed capture error. If `capture` returns `Err` while the
  `StreamPreparation` is simply dropped, `Drop` records "abandoned" as the
  primary and the cause is gone. Note that the only fallible step in the
  candidate's capture is `with_object_store_registry` →
  `RuntimeEnvBuilder::build_arc()`, which at 55.2.0 cannot fail for a builder
  made by `from_runtime_env` (no `disk_manager_builder`; it clones the disk
  manager, memory pool and registry Arcs and rebuilds the cache manager from
  the same caches, `runtime_env.rs:519–548`). The rule still has to be stated
  because the shape invites later fallible steps.
- **1.2 Registry overlay without re-capture.** `ScopedSession::
with_object_store_registry` rebuilds only `self.runtime`;
  `self.state.runtime_env()` keeps the parent's runtime (`scoped.rs:65–73`).
  Through the `Session` trait the overlay is what callers see
  (`runtime_env()` returns `&self.runtime`; `create_physical_plan` passes
  `self` as `&dyn Session`; `task_ctx()` is `TaskContext::from(self as &dyn
Session)`, which copies `session_id`, `config`, the four function maps and
  `runtime_env()` from the trait, `datafusion-session/src/session.rs:209–223`).
  So the characterization's "child registry at captured planning" is by
  construction, and a `TaskContext` derived from the snapshot keeps the overlay
  with no second capture. The one way to lose it is a `SessionState` downcast,
  which the draft already forbids; add that `ScopedSession::analyze`,
  `optimize` and `create_physical_expr` run on `self.state` and therefore see
  the parent runtime, which is harmless for those three (no store access) but
  is the boundary to keep in mind if more state-backed methods are added.
- **1.3 Execute from the saved view (check 4) is already expressible.**
  `ScopedTaskContext::from_resources(&snapshot.task_ctx(), resources)` yields a
  task context with the snapshot's config (7 in the test), functions, overlay
  runtime and the scope extension; `from_resources` clones the parent's config
  and reuses `parent.runtime_env()` (`task_resources_context.rs`). Since
  `ScopedSession::new` already set the `TaskResourceScope` extension on the
  captured config, the extension is set twice with the same `Arc`; the
  `Arc::ptr_eq` guard in `ScopedTaskContext::with_object_store_registry` passes.
  The implementation of consuming execute is therefore `execute`'s body with
  `context.task_ctx()` replaced by `self.session.task_ctx()`; nothing else in
  the error/cancel/reap sequence changes.
- **1.4 Drop and lifetime.** A captured object owning a `ScopedSession` holds a
  full `SessionState` clone: config (with the scope `Arc`), function maps,
  analyzer/optimizer/planner `Arc`s, catalog list, the parent `RuntimeEnv` and
  the overlay. Dropping it unexecuted behaves as today: `StreamPreparation::Drop`
  → abandoned → cleanup spawned on the runtime → reaped later. Because
  `ManagedStreamControl`'s `Inner` also holds `resources`, `TaskResourceScope::
Drop` cannot be relied on for cancellation and the explicit drain remains the
  only qualification (as the code comments say). Memory, not correctness.
- **1.5 One-shot (check 3).** `capture(self: Box<Self>)` is one-shot by
  construction; `ScopedSession` is not `Clone`; `session(&self)` is a borrow.
  `ScopedSession::task_ctx()` does hand out an owned `Arc<TaskContext>` that
  could be fed to `execute_stream` directly, bypassing the preparation; that is
  possible with any task context today and is not introduced by the candidate.
- **1.6 Stop before, during and after planning (check 2).** Before: the
  `cancelled().now_or_never()` check. During borrowed planning: the caller
  selects `snapshot.create_physical_plan(&plan)` against
  `resources.cancelled()` on its own task (the `cancelled` doc says exactly
  this). "Cannot invoke a refused physical factory" holds for factories that
  register through the scope (sealed → `Execution` error); a factory that
  ignores the scope still runs, as today. After: `execute`'s cancellation check
  runs before `execute_stream`. No gap found beyond the pre-existing one.

## 2. Graph analysis vs later materialization; provider lifetime

**Delta.** `load_delta_read_state(ctx: &dyn Session, …)` takes
`ctx.runtime_env().object_store(&url)` and builds `log_store` from it
(`table/mod.rs:826–829`); `DeltaTableSource { snapshot, log_store, config,
schema, file_selection }` retains it (`logical/table_source.rs:39–45`) and
`with_file_column`/`with_row_index_column` clone it into new sources. At
physical planning `table_scan_planner.rs:138` takes `source.log_store()`;
`physical_plan/planner/log_scan.rs:269` reads commits and checkpoints through
`ctx.log_store()` → `log_store.object_store(None)` (`delta_log/*.rs`,
`checkpoint/mod.rs`); `change_data_feed.rs:225,680` and
`physical_plan/commit_exec.rs:451,484,783` read and **write** through it;
`ddl.rs`, `lake_source.rs` and `inspection/history.rs` likewise. The data
files, by contrast, are read through the _planning_ Session:
`datasource/scan.rs:474` resolves `session.runtime_env().object_store(&url)`
and installs the reader factory from it.

Consequences, confirmed by source:

- A Delta logical plan is owner-bound at creation: log, CDF and commit I/O go
  through the store resolved by the Session that created the source; file I/O
  goes through the Session that plans the scan. With one registry the split is
  invisible. With a per-attempt registry (the `registry` argument of
  `capture`), rotated credentials, or a sealed analysis owner, an analysis-time
  plan executed under a later attempt reads the log from one lineage and the
  files from another; a `commit_exec` under that plan commits through the
  analysis-time store while the attempt's writer wrote files through its own.
  The draft's warning ("do not finish a graph-analysis owner, keep a logical
  plan containing an owner-bound store, and assume it can run under a fresh
  attempt owner") is therefore a Delta fact, and for writes it is a
  correctness hazard rather than only a lifetime one.
- The retained log store is a plain `Arc<dyn ObjectStore>`: it is not
  scope-bound, so a sealed or drained analysis scope does not refuse its I/O.
  That I/O is unowned in the draft's sense.
- The direction that removes the hazard is Delta-side, out of this review's
  scope: resolve the log store from the executing Session at physical planning
  (the `table_scan_planner` already has `session`) instead of carrying it in
  the logical source. Until then, Delta plans must be re-resolved under the
  attempt owner, not reused from analysis.

**Iceberg.** `IcebergScan` retains no store: its fields are the table URI,
schema and schema history, name mapping, format version, snapshot, partition
specs and Arrow schemas (`datasource/scan.rs:79–100`). `create_physical_plan`
re-acquires `base_store = get_object_store_from_session(session, &table_url)`
(`scan.rs:1090–1091`); `scan_with_merge_metadata` and `scan_metadata_as_data`
re-acquire through `session.runtime_env().object_store(...)` (`:1137`,
`:1377`), as does `scan/planning.rs:70`. Source creation loads the table
through `StoreContext::new(object_store, &table_url)` from the creating
Session (`lake_source.rs:406`) and drops it. So Iceberg already follows "store
from the executing Session"; what remains is what the draft lists: the
creation-time metadata I/O runs under the creating owner, unsupervised unless
the store itself is scope-wrapped, and `io/deletion_vector.rs:221` and
`metadata_relation/mod.rs:150,365` build their own `StoreContext`s from stores
passed in (not traced further here).

**Batch pipelines (the units on the root).** `materialize.rs` builds
`GraphScope::new(graph, &analyzed.relations, flow)` and resolves a flow's query
against the _analysis-time_ relations; at least temporary views' plans are
reused verbatim (tables are installed as placeholders during analysis and read
again at materialization; whether `AnalyzedGraph.relations` holds a full plan
for tables after analysis was not re-checked for this review). A view over a
Delta table therefore carries an analysis-time `DeltaTableSource` into
materialization: the Delta split in this section applies to batch pipelines
today, independent of the capture candidate. The bounded lowerer does not
reuse analysis plans; it re-resolves over explicit bindings and provider
identity, so it is unaffected. This is the caller trace the draft asks for in
"Batch currently analyzes plans for later materialization"; the conclusion is
that for owner-bound providers the analyzed artifact must be rebound or
re-resolved under the attempt owner, and the clock point in §3 gives a second,
provider-independent reason.

## 3. Cluster capability, worker transport, execution start

- **Default unsupported is already explicit.** `JobRunner::begin_preparation`
  defaults to `NotImplemented("pre-planning preparation is not supported by
this runner")` (`session/job.rs:33–37`); only `LocalJobRunner` overrides it
  (`local.rs:98, 276`); `ClusterJobRunner` inherits the default
  (`job_runner.rs:52`). The candidate's `capture` needs the same default and the
  same rule that `JobService` must not fall back to legacy `execute` under a
  captured guarantee.
- **The caller's task context does not reach workers.**
  `ClusterJobRunner::execute` sends `DriverMessage::ExecuteJob { plan, context:
ctx.task_ctx(), … }` (`job_runner.rs:58–67`); the driver stores it in the
  `JobDescriptor` and uses it for two things: encoding task definitions
  (`job_scheduler/core.rs:695` returns `(definition, job.context.clone())`; the
  codec's `try_encode`/`try_decode` take `&TaskContext` and use only
  `ctx.runtime_env()` and `ctx.memory_pool()`, `proto/codec.rs:377…`), and
  driver-local storage-stream cleanup (`JobAction::CleanUpJob { context }` →
  `TaskRunnerMessage::CleanUpStorageStreams { context }` →
  `streams.remove_streams(job_id, stage, &context)`,
  `driver/actor/handler.rs:518–545`, `task_runner/actor/handler.rs:407–416`).
  Workers run tasks with `self.options.session.task_ctx()`, their own
  `SessionContext` (`worker/actor/core.rs:124`); scans travel as
  `object_store_url` strings resolved against the worker's registry
  (`codec.rs:570–637, 744`). Hence a registry overlay supplied at capture
  changes driver-side planning, encoding and cleanup only; worker I/O is
  unaffected and silently so. Until a worker-resolvable form exists (URL-keyed
  registration shipped with the task, or worker-side admission), cluster
  `capture` with a registry must return unsupported rather than accept it.
  Config captured in the snapshot (`target_partitions` 7 in the test) likewise
  does not reach workers.
- **Execution start.** `SessionContext::state()` clones the state and calls
  `mark_start_execution` (`context/mod.rs:2054–2058`), which sets
  `query_execution_start_time = Utc::now()` (`execution_props.rs:98–99`);
  `task_ctx()` on a `SessionContext` derives from the read-locked authority
  (`:2038–2040`, `:2165–2169`), and `TaskContext` carries no execution
  properties at all (`session_state.rs:2316–2330`). So every
  `ScopedSession::new(context.state(), …)` fixes the clock for that snapshot,
  the clock is consumed at logical simplification (Sail's `TimestampNow::simplify`
  reads `query_execution_start_time`), and a second capture is a new clock, as
  the draft says. For pipelines this is the provider-independent reason not to
  reuse analysis-time plans at materialization: a `current_timestamp()` folded
  during analysis would be replayed at every later attempt. It is also what the
  CF-0186 lowering tests pin from the other side: in the lowerer the clock is
  fixed at the attempt's planning and the plan is marked non-replayable.

## 4. On the candidate shape

- `fn capture<'a>(self: Box<Self>, registry: Option<Arc<dyn
ObjectStoreRegistry>>) -> Result<Box<dyn CapturedJobPreparation + 'a>>
where Self: 'a` is consistent with the borrowed-runner lifetime already on
  `LocalJobPreparation<'a>`; the standalone probe's E0597 is the property the
  real type also has.
- Prefer validating the registry (building the overlay runtime) _before_ any
  state that would need `fail` on error, or route the error through `fail`
  (§1.1). Either way the captured object must own the `StreamPreparation` so
  that exactly one of `complete`/`finish`/`cancel`/`fail` runs.
- `CapturedJobPreparation::session(&self) -> &ScopedSession` is enough for the
  resolver's analyzer-only mode (`analyze`) and for physical planning; the
  typed opt-in accessor the draft defers is the right place to expose it, and
  `with_query_session`'s generic `Session` behaviour should stay as documented.
- Nothing in the candidate ties a physical plan to the capture that planned
  it; the same is true today of `execute(plan)`. If that guarantee is wanted,
  it is a separate decision (a plan token minted by `session()`), not part of
  this draft.

## 5. Not reviewed, open

- Celeborn and non-storage shuffle cleanup paths, `io/deletion_vector.rs` and
  `metadata_relation` store construction, and whether `AnalyzedGraph.relations`
  holds full table plans after analysis (§2) were not traced.
- No live backend verdicts: all of the above is source reading at the pinned
  root.
- The Status-rendering question (CF-0120/0121) is unchanged; the A–D units and
  the C5 manifest are unaffected by this review.

## 6. Follow-up (CF-0210): what survives raw-stream disposal and settlement

Codex's remaining question: a `TaskContext` keeps only a subset of the
captured `SessionState`; which dependencies survive disposal of the raw
stream and settlement of registered I/O? Traced at the same root.

**What a `TaskContext` owns.** `session_id`, `task_id`, a `SessionConfig`
(the `Arc<ConfigOptions>` and the typed `extensions` map), the four function
maps, and `Arc<RuntimeEnv>` (`datafusion-execution/src/task.rs:52–69`;
`From<&SessionState>` copies exactly these, `session_state.rs:2316–2330`;
`From<&dyn Session>` the same, `datafusion-session/src/session.rs:209–223`).
Because the extensions map travels, every session extension Sail installs
(`CatalogManager`, `TaskResourceScope`, `DataSourceRegistry`, `PlanService`,
the Delta table cache) is reachable at execution through
`SessionExtensionAccessor for TaskContext` (`sail-common-datafusion/src/
extension.rs:56`). What is not carried: analyzer, optimizer, physical
optimizers, query planner, catalog list, table options, execution props,
statistics registry.

**None of the missing parts is read at execution.** Physical plan nodes own
their dependencies by `Arc` (providers, UDF implementations, Delta
`log_store` in `commit_exec`); file scans resolve their store from the task
context at open (`datafusion-datasource/src/file_scan_config/mod.rs:706`,
`context.runtime_env().object_store(&self.object_store_url)`). A grep of
Sail's `physical_plan`, `physical`, `datasource` and `sail-execution` trees
for `SessionState` outside tests finds two things: the codec's function
defaults (`proto/codec.rs:3587, 4497`) and `scan_by_adds_exec.rs:88, 201`,
which _rebuilds_ a `SessionState` at execution from
`self.context.session_config().clone()` and `self.context.runtime_env()`, so
it inherits the snapshot's config and overlay runtime and nothing else from
the captured state. No execute-time path borrows the captured
`SessionState`.

**Disposal and settlement own what they need.** `Inner` owns `resources` and
`runtime`; `Cleanup` owns `Arc<Inner>`, the raw stream and the primary error
(`managed_stream.rs:316–322`). `dispose()` drops the stream under
`catch_unwind`, then `run()` awaits `resources.drain()`, which joins every
registered task; registered factories are `'static` closures moved into
`runtime.spawn` (`task_resources.rs:159–199`), so each task owns its captures
(stores, writers, clients) by value. The join report is published to
`completion`. Therefore what survives disposal is exactly what plan nodes and
spawned tasks own by `Arc`; the stream wrapper does not need to retain the
captured state, and the full `ScopedSession` is needed only while `session()`
is in use for resolution and planning. The one reference-shaped dependency is
the runner borrow on the preparation (`&'a LocalJobRunner`), used by `reap`,
which does not reach streams or tasks.

**Shared causes.** `Inner::drain` already returns the admission error as
`DataFusionError::Shared(error)` while pushing the same `Arc` into the
report's failures; a synchronous `capture` can do the same with its typed
cause: `fail` with one `Arc`, return `Shared` of it, no stringification.

Residuals unchanged: `Cleanup::Drop` on runtime shutdown publishes
"interrupted before drainage completed"; worker-side ownership is the
worker's own session (§3).

## 7. Candidate review (CF-0212): `7505e2ced` on shared contract `16c43aa29`

Pins: `16c43aa29` adds `JobPreparation::capture` (default: `self.cancel()` then
`NotImplemented`) and `trait CapturedJobPreparation: JobPreparation { fn
session(&self) -> &ScopedSession }` (`session/job.rs`); `7505e2ced` adds
`local/preparation/captured.rs`, `execute_with_snapshot` in
`local/preparation.rs`, and tests in `captured_preparation_tests.rs` and
`capture_boundary_tests.rs`. Read only.

**Construction.** `capture_snapshot` runs under `catch_unwind`: cancelled
check (`resources.cancelled().now_or_never()`), `ScopedSession::new(
self.context.state(), resources)`, optional `with_object_store_registry`.
On `Err`, the cause is wrapped once in an `Arc`, `preparation.fail(Shared(arc))`
runs, and `Shared(arc)` is returned, so the caller's error and the report's
primary are the same allocation; the test asserts `Arc::ptr_eq`. This is the
§1.1 rule implemented. The `catch_unwind` also covers `context.state()`,
whose read lock is `parking_lot` (no poisoning), and the drop of a failed
`ScopedSession`; a panic there is labelled `"capture"`. Fine.

**Cancellation races.** The cancelled check and `state()` are not atomic, so a
`stop()` landing between them yields a captured object over a cancelled
scope. Benign: `stop_jobs` calls `control.cancel()`, which for a `Preparing`
phase calls `resources.cancel()` (admission sealed, cancellation latched) and
sets `canceled`; any factory registering through the scope during borrowed
planning is refused with `"task resource scope is sealed"`, and
`execute_with_snapshot` re-checks `cancelled()` before planning the stream
and takes the `preparation.cancel()` path. `stop_jobs` then awaits
`control.completion()`, which completes only when the holder ends the
preparation (`fail`/`finish`/`cancel`/`complete` or `Drop`), exactly as for a
legacy preparation held across planning; nothing new blocks or leaks. The
`captured_stop_refuses_factory_and_unpolled_execute_never_starts_it` test
covers both orders for the execute boundary; the borrowed-planning refusal
rests on the planner using the scope, as noted in §1.6.

**Execute from the snapshot.** `execute_with_snapshot(plan, Some(session))`
derives `session.task_ctx()` (config 7, functions, overlay runtime, scope
extension already set by `ScopedSession::new`), wraps it with
`ScopedTaskContext::from_resources` (same `Arc`, set again, harmless), and
drops the `ScopedSession` inside the closure before `execute_stream`. That is
the §6 conclusion in code: no execution borrows the captured state. The
`captured_bound_execution_preserves_planning_snapshot` test pins 7/child at
planning and at execution beside the unchanged legacy 7/child → 9/parent.
`None` keeps the late authority capture byte-for-byte.

**Dependency and drop ownership.** `CapturedLocalJobPreparation { preparation,
session }` drops `preparation` first (`StreamPreparation::Drop` → abandoned →
cleanup spawned) then `session`; since drain joins tasks rather than counting
`Arc`s, the order does not matter for settlement. The
`captured_guard_finish_cancel_and_drop_keep_registered_cleanup_owned` test
holds a registered supervisor across all three transitions and shows the job
stays active until release and `result()` is `Ok` only for `finish`. The
`captured_registry_survives_raw_stream_disposal_until_registered_io_settles`
test is the §6 claim made observable: the weak registry is alive after the
output stream is dropped (held by the task-owned `TaskContext`), still alive
while the registered I/O is held, and gone after drain. Good.

**Findings.**

- **7.1 A second `capture` on a captured object cancels the job.** Because
  `CapturedJobPreparation: JobPreparation`, the captured object inherits the
  default `capture`, which calls `self.cancel()` before returning
  `NotImplemented`. One-shot is thus enforced destructively: a caller that
  mistakenly captures twice loses the admitted job with a capability error
  whose text ("not supported by this runner") misdescribes the cause.
  Override `capture` on `CapturedLocalJobPreparation` (or on the trait as a
  provided method) to return a typed "already captured" error without
  cancelling, or document that a second capture is a cancel. Draft check 3
  is the place to say which.
- **7.2 The registry argument replaces, it does not overlay.**
  `with_object_store_registry` rebuilds the runtime with the supplied registry
  wholesale (`scoped.rs:65–73`, `RuntimeEnvBuilder::with_object_store_registry`),
  so URLs registered only in the parent runtime become unresolvable in the
  snapshot ("No suitable object store found"). The tests register the one URL
  they use. The contract comment ("must already have qualified
  ownership/routing") is right; the word "overlay" in the draft is not. State
  that a supplied registry must be complete for the plan, or compose it over
  the parent's registry explicitly.
- **7.3 Panic path of capture is untested.** The only fallible step at 55.2.0
  is unreachable (§1.1), so `fail` is exercised through cancellation only;
  the panic branch (`panic_error("capture", …)`) has no fixture. Low risk;
  worth one test if the branch is to be relied on.
- **7.4 Borrowed planning after `stop`.** Nothing refuses
  `session().create_physical_plan` on a cancelled scope; refusal happens when
  a factory registers (sealed) or at execute. That matches the legacy boundary
  and the draft's check 2 wording, so no change is asked; it is recorded so
  the resolver's analyzer-only opt-in does not assume planning itself is
  cancelled.

Nothing else found. No code, no scope change; A–D/E′/Status untouched.
