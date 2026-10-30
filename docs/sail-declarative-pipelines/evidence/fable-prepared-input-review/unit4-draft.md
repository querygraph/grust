# Bounded-plan admission and lowering for streaming flows (unit 4 design)

Status: design draft for Codex review (CF-0039 answer), before any Sail edit.
It fixes the seam between the Fable streaming/CDC components already offered
(units 2, 3, 5) and the execution machinery Codex owns. Pinned references:
Spark 4.2.1 `617618396`; Sail base `779cb136d`; Fable branch head listed in
the coordination log; design review `SDP-FABLE-DESIGN-REVIEW.md` §4.1, §5.2,
§5.7; `LOCAL-STREAM-OWNERSHIP-DESIGN.md`; Fable packets `fable-streaming-prepared`
and `fable-iggy-harness`.

## 1. What a microbatch is

Spark SDP runs every streaming flow with `Trigger.AvailableNow`
(`TriggeredGraphExecution.scala:77`): the frontier is captured once, each
microbatch is an ordinary batch plan over explicit ranges, logged as intent
before execution and replayed with the same ranges after a failure. Sail
reproduces exactly that, as the design review recommends: a microbatch is a
**bounded `LogicalPlan`** whose streaming inputs are **recorded range scans**,
optimised and executed through `JobService` like today's batch flows.

Authority: the recorded `BatchIntent` (unit 3, `pipelines/streaming/intent.rs`).
Lowering never recaptures a frontier, never calls `frontier()` or `earliest()`,
and never infers progress from output rows. It consumes `(RunFrontier,
Progress, BatchIntent)` as read from the run record and produces plans.

## 2. The seam: relation binding through `RelationScope`

Today `analysis::GraphScope` implements `sail_plan::resolver::scope::RelationScope`
to bind graph-local names to already-resolved plans while recording reads
(`analysis.rs:20–75`), and `execution::run_command` resolves a flow query with
that scope through `resolve_and_execute_plan_with_scope` and runs it on
`JobService` (`execution.rs:96–115`). Unit 4 adds one more scope, composed with
`GraphScope`, and nothing else in the resolver:

```text
BoundedScope<'a> {
    graph:  &'a GraphScope<'a>,             // local outputs, as today
    intent: &'a BatchIntent,                // the recorded ranges
    scans:  &'a BTreeMap<SourceRef, Arc<dyn TableProvider>>,  // one provider per range, built by the adapter
    reads:  Mutex<BTreeSet<SourceRef>>,     // which recorded ranges the plan consumed
}
impl RelationScope for BoundedScope {
    fn resolve(name) -> Option<LogicalPlan>:
        if name is a graph output          -> graph.resolve(name)            (unchanged path)
        else if name is a recorded source  -> union of the range scans for that source in the intent,
                                              as a TableScan over the adapter's bounded provider; record the read
        else                               -> None                            (catalog resolution as today)
}
```

- **Local graph outputs** resolve exactly as now: `GraphScope` returns the
  resolved plan of an upstream output (its materialised relation or empty
  relation with the inferred schema). A streaming read of a local streaming
  table (`readStream.table(local)`) is a recorded source whose adapter is the
  lakehouse-table range source (design review §4.4), not a recapture.
- **External streaming-source references** (an Iggy topic, a table version
  range) resolve only through the intent. A name that is streaming but has no
  range in the intent is an admission error, never a fallback to a catalog
  read: the whole point of the frontier record is that the plan cannot see
  data outside it.
- `is_streaming_query_plan` stays the definition-time classifier; after
  binding, the bounded plan is a batch plan and is planned by the batch
  planner. The existing streaming rewriter (`sail-plan/src/streaming/rewriter.rs`),
  which rejects sort, aggregate, join, window and repartition, is **not** on
  this path; those operators are admitted or rejected by section 4, not by
  the rewriter.

The scan node is an ordinary `TableScan` over the adapter's `TableProvider`
(`BoundedSource::scan`, unit 3). For a single process that is sufficient; a
distributed run needs the range descriptor in the physical plan codec, which
the design review already scoped (§4.1, "the only codec work") and which is a
separate unit under Codex's physical protobuf ownership.

## 3. Operation-specific context

Each microbatch runs under a context derived from the session context, not a
fresh one, so that nothing the session configured is lost:

| Must be preserved | How |
| --- | --- |
| function registry, type planner, UDFs | derive from `SessionContext::state()` (same `SessionState` clone the batch flows use); never `SessionContext::new()` |
| `PlanConfig` and flow `sql_conf` overrides | `SparkSession::plan_config_with_overrides(flow.sql_conf)` exactly as `analysis.rs:101` does; the overrides are part of the unit-5 `EvaluationContext` |
| catalog manager and extensions | the session's extensions are reachable through the derived state; no new catalog path |
| resource scope | one `TaskResourceScope` per batch attempt, owned by the preparation owner (`LOCAL-STREAM-OWNERSHIP-DESIGN.md` §"Prepared-stream ownership"); sealing it cancels the attempt; the next attempt gets a new scope |
| object-store routing for checkpoint writes | Codex's owned-effect adapter (`checkpoint-effect-adapter-design`); the batch context must carry whatever runtime-env overlay that design selects, which is why the context is derived by a single constructor owned with the execution code, not assembled in the streaming module |

Concretely: a `BatchContext { state: SessionState, config: Arc<PlanConfig>,
scope: TaskResourceScope, intent: BatchIntent, identity: InputIdentity }` built
by one function in the execution module (Codex's side of the seam), consumed
by the lowering function (Fable's side).

## 4. Admission: the stateless subset, explicitly

Admission classifies the bound plan before any execution. Only operators whose
semantics on a bounded range equal Spark's AvailableNow semantics without
cross-batch state are admitted. The classification is a visitor over the
bound `LogicalPlan` and returns **evidence**, not just a verdict:

| Operator | Decision | Reason |
| --- | --- | --- |
| Projection, Filter, Limit-less Union, scalar UDF | admit | row-local |
| Join where every input is a recorded range or a local batch output of this run | admit | one batch over fixed ranges (design review §5.2: "a join or union of two streams is one batch over two ranges") |
| Aggregate without watermark, Window, Sort, Limit, Distinct, stream-stream join with state across batches | reject, listed | AvailableNow aggregates and stream-stream joins need durable cross-batch state (handoff item 4); batch support of the operator does not establish streaming semantics |
| Repartition | admit, noted | no semantics; the private branch's removal is not ported |
| Auto CDC flow | admit the source read only; the CDC steps run on the executed rows through units 2 and 5, not as plan operators | validation must see original rows |
| Any `TableScan` not bound through `BoundedScope` (catalog table) | reject | would read outside the intent |

`AdmissionEvidence { admitted: bool, operators: Vec<(name, decision, reason)>,
sources_read: Vec<SourceRef>, unbound_streaming_names: Vec<Name> }` is
serialisable and goes into the run record next to the intent. Rejections are
Sail conditions, visible in coverage as unsupported cases; nothing is silently
widened.

## 5. Pure lowering

```text
lower(ctx: &BatchContext, graph: &GraphDefinition, flow: &Flow)
    -> Result<Lowered { plan: LogicalPlan, evidence: AdmissionEvidence, identity_digest: String }>
```

- resolves `flow.query` with `PlanResolver::new(&ctx.state_context,
  ctx.config).with_relation_scope(&BoundedScope{..})`;
- runs admission on the resolved plan;
- returns the bounded logical plan and evidence. It has **no target effect**:
  no `WriteTo`, no `MERGE`, no checkpoint write, no acknowledgement. The unit-5
  `InputIdentity` is built here from the intent and the evaluation context,
  so validation receipts and sealed content bind to what was actually lowered.

Execution of the lowered plan, the write, the unit-5 seal and the progress
record form the **effect barrier**, which is Codex's execution/effect design.
`execution::execute`'s rejection of any pipeline with Table or Sink outputs
("incremental pipeline execution") **stays** until that barrier qualifies the
path; removing it is not part of lowering. A dry run can call `lower` for
every batch of a captured frontier and report evidence without executing.

## 6. Adapters and the synchronous `BoundedSource`

Unit 3's `BoundedSource` is synchronous because the deterministic source is in
memory. Iggy's frontier (`get_topic` partition `current_offset`), earliest
(first retained offset) and scan (poll by offset with context) are network
calls. Two rules:

1. **The control loop is async; adapters are async.** Change the contract to
   `async fn describe / earliest / frontier / scan` behind `async_trait`
   (already a workspace dependency), with `plan_end` staying synchronous and
   pure. The deterministic source implements the async methods trivially; no
   runtime thread is blocked, and the Iggy adapter awaits the SDK inside the
   batch's `TaskResourceScope` so cancellation seals it.
2. **No Iggy types cross the seam.** The adapter lives in its own crate
   (`sail-data-source` behind the existing `iggy` feature, where the pinned
   sail-iggy work already sits) and exposes only `BoundedSource`; cursors are
   `pos:<offset>` tokens and incarnations the `PartitionContext.incarnation`
   rendered as a token. The control model (`pipelines/streaming`) never links
   the client.

What the pinned-broker observations (`fable-iggy-harness`) force into the
adapter: compare the first returned offset with `start` and fail closed
(retention resumes silently); carry the incarnation on every range and treat
`HistoryUnavailable` (87) as "drop the position, report"; treat an accepted
acknowledgement as advisory while the SDK is reconnecting (it retained and
replayed a store issued while the broker was down); acknowledge only after
SDP's own durable progress record, never before.

## 7. What this unit does and does not touch

Fable edits for unit 4 after review: new `pipelines/streaming/{scope.rs,
admission.rs, lower.rs}` and tests over the deterministic source; the
`async` change in `source.rs`/`test_source.rs`; the Iggy adapter as a later
separate unit. The `BatchContext` constructor and any change to
`execution.rs`, `analysis.rs`, `JobService` or the physical codec are
coordinated edits on Codex's side of the seam, each declared before it is
made. No frontier capture, progress record, write, MERGE or acknowledgement is
implemented by this unit.

## 8. Open questions for Codex

1. Does the owned-effect adapter's runtime-env overlay need to be part of
   `BatchContext` at lowering time, or only at execution? If the former, the
   constructor belongs with that design.
2. Is `resolve_and_execute_plan_with_scope` the right entry for the bounded
   plan, or should lowering return the `LogicalPlan` and let the effect
   barrier call `JobService` directly? The draft assumes the latter.
3. For distributed runs, should the range descriptor be a `oneof` arm in
   `physical.proto` now or after the local path is qualified? The draft
   assumes after.
