# Bounded-plan admission and lowering for streaming flows (unit 4 design)

Status: design draft for Codex review, revised after CF-0044; no Sail edit for
unit 4 yet. Revision marks are inline ("Revised:").
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

- **Revised: read mode is bound before resolution, not recovered from a
  name.** `RelationScope::resolve` receives only a name, and
  `sail-plan/src/resolver/query/mod.rs` discards `Read.is_streaming` on the
  way in, so a name-only scope cannot tell a batch read of a local output
  from a streaming read of the same name. Lowering therefore walks the flow's
  `spec::QueryPlan` **before** calling the resolver and rewrites every
  `Read { is_streaming: true, NamedTable(name) }` into a reference to a
  bound range of the intent: a reserved, unspellable qualified name
  (`__sdp_bounded__`, `<intent id>`, `<source ref>`) that `BoundedScope`
  resolves to the union of the recorded range scans and that `GraphScope`
  can never see. Any streaming read left unbound after the walk is an
  admission error; any batch read of a local output resolves through
  `GraphScope` as today, to its materialised relation or, during analysis,
  to the schema-only `EmptyRelation`. A streaming read of a local streaming
  table is a recorded source whose adapter is the lakehouse-table range
  source (design review §4.4); it is never resolved by name, so it can
  neither become the empty placeholder nor an ordinary catalog read. Proof
  obligation in tests: a flow with a batch read and a streaming read of the
  same local name lowers to one `GraphScope` relation and one bound range.
- **Revised: absent binding versus recorded empty intent.** A source with no
  range in the intent is an absent binding and an admission error. A source
  whose recorded range is empty (`start == end` under the captured
  incarnation, or an intent with zero rows) lowers to an empty bounded input
  with the source schema; the batch still runs, its unit-5 manifest seals
  with zero rows, and it keeps its completion obligation.
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
| `PlanConfig` and flow `sql_conf` overrides | `SparkSession::plan_config_with_overrides(flow.sql_conf)` exactly as `analysis.rs:101` does. Revised: the unit-5 `EvaluationContext` today records only case, keys, sequencing text, delete condition and column selection; unit 4 extends the sealed identity with an **evaluation snapshot** (the resolved `PlanConfig` fields that change expression semantics: case sensitivity, ANSI mode, session time zone, the flow `sql_conf` overrides verbatim) and a **source-binding identity** (the intent id and, per bound source, its descriptor digest and the range list). Nothing is claimed to be in the seal until that struct carries it. |
| catalog manager and extensions | the session's extensions are reachable through the derived state; no new catalog path |
| resource scope | Revised: the runner's existing preparation owner and its one existing `TaskResourceScope` cover preparation, lowering and execution of the attempt; lowering never creates a scope of its own. `TaskResourceScope::seal` only closes admission; `cancel` seals **and** latches cancellation. Cancelling an attempt means `cancel`, and the next attempt is a new owned attempt under the runner, not a scope minted in lowering |
| object-store routing for checkpoint writes | Codex's owned-effect adapter (`checkpoint-effect-adapter-design`); the batch context must carry whatever runtime-env overlay that design selects, which is why the context is derived by a single constructor owned with the execution code, not assembled in the streaming module |

Concretely: one operation-owned `BatchContext { state: SessionState, config:
Arc<PlanConfig>, scope: &TaskResourceScope, intent: BatchIntent, identity:
InputIdentity }` built by one function in the execution module (Codex's side
of the seam) and used for preparation, lowering **and** execution of the
attempt, because provider and schema actions may already perform I/O during
planning; its runtime overlay (the owned-effect adapter's object-store
routing) is derived before those actions. Lowering (Fable's side) consumes it
and never constructs one.

## 4. Admission: the stateless subset, explicitly

Admission classifies the bound plan before any execution. Only operators whose
semantics on a bounded range equal Spark's AvailableNow semantics without
cross-batch state are admitted. The classification is a visitor over the
bound `LogicalPlan` and returns **evidence**, not just a verdict:

| Operator | Decision | Reason |
| --- | --- | --- |
| Projection, Filter, Limit-less Union, deterministic scalar expressions and UDFs declared deterministic | admit | row-local, replayable |
| Join of a recorded range with a **static side** (a local batch output materialised before this batch, or a catalog table read at a pinned version) | admit, with the static side's identity in the evidence | the static side does not change within the batch; the stream side is one range |
| Join of two recorded ranges (stream-stream) | **reject**, listed | Revised: a key on the left in batch 1 and its match on the right in batch 2 needs cross-batch state; joining only the two current ranges misses it. The design review's "one batch over two ranges" describes range capture, not join semantics. Admitted only when the stateful contract exists, with reference tests |
| Projection or Filter containing a volatile or nondeterministic expression or UDF (`rand`, `uuid`, `current_timestamp`, a UDF not declared deterministic) | admit the plan, but mark the batch **non-replayable in content**: the unit-5 identity records the volatility and validation/dedup run once over one materialised evaluation, never re-evaluated under the same receipt | Revised: no broad scalar-UDF admission; evaluation must not differ between validation and dedup |
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
path; removing it is not part of lowering. Revised: the public dry run stays
what Spark's `PipelineExecution.dryRunPipeline` is, resolution and
validation; it captures no frontier and plans no batch. A diagnostic
`lower` over an explicitly supplied recorded intent is a separate, internal
use for tests and evidence, never the dry-run command.

## 6. Adapters and the synchronous `BoundedSource`

Unit 3's `BoundedSource` is synchronous because the deterministic source is in
memory. Iggy's frontier (`get_topic` partition `current_offset`), earliest
(first retained offset) and scan (poll by offset with context) are network
calls. Two rules:

1. **The control loop is async; adapters are async.** Change the contract to
   `async fn describe / earliest / frontier / scan` behind `async_trait`
   (already a workspace dependency), with `plan_end` staying synchronous and
   pure. The deterministic source implements the async methods trivially and
   no runtime thread is blocked. Revised: an SDK future awaited in an unowned
   planning task is not made safe by calling `cancel`; every adapter call
   runs inside a task spawned through the attempt's `TaskResourceScope`
   (`spawn`), so the owned supervisor is what cancellation latches and what
   drain joins. The provider the adapter returns carries a disposition the
   owner can drive: on reconnect or a replayed request it re-checks the
   first offset and incarnation before yielding rows; on a retention gap it
   fails closed; on cancellation it drops its consumer without acknowledging.
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

## 8. Questions and Codex's answers (CF-0044)

1. Overlay at lowering or execution: **the same operation-owned context covers
   preparation, lowering and execution**, with its runtime overlay derived
   before any provider or schema action; the runner's existing preparation
   owner and one existing `TaskResourceScope`, never a scope created in
   lowering (folded into §3).
2. Entry point: **return the bounded `LogicalPlan` plus evidence**; lowering
   never calls `resolve_and_execute_plan_with_scope`; execution goes through
   the admitted `JobService`/effect barrier with that same context (§5).
3. Codec: **defer the arm for the local planning component**, but require an
   exact codec round trip and worker adapter qualification before any
   distributed admission; never dispatch an unencoded range scan as an
   ordinary table read (§2).

Original questions, kept for the record:

1. Does the owned-effect adapter's runtime-env overlay need to be part of
   `BatchContext` at lowering time, or only at execution? If the former, the
   constructor belongs with that design.
2. Is `resolve_and_execute_plan_with_scope` the right entry for the bounded
   plan, or should lowering return the `LogicalPlan` and let the effect
   barrier call `JobService` directly? The draft assumes the latter.
3. For distributed runs, should the range descriptor be a `oneof` arm in
   `physical.proto` now or after the local path is qualified? The draft
   assumes after.


## 9. Revision log

- After CF-0044: read mode bound before resolution through a reserved
  qualified name (§2); absent binding versus recorded empty intent (§2);
  stream-stream joins rejected until the stateful contract exists, static-side
  joins admitted with identity in evidence, volatile expressions marked and
  evaluated once (§4); evaluation snapshot and source-binding identity named
  as additions to the sealed identity rather than claimed present (§3);
  `seal` versus `cancel` corrected, one owned scope per attempt from the
  runner (§3); public dry run stays resolution/admission (§5); adapter calls
  owned by the attempt's scope with an explicit provider disposition (§6).
