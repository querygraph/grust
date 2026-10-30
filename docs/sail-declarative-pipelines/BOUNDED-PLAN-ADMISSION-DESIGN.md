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

| Must be preserved                          | How                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| function registry, type planner, UDFs      | Revised after CF-0125: borrow the **authoritative** `SessionContext` and build `PlanResolver::new(ctx, ..)` on it, as `analysis.rs` does; no `SessionState` clone and no new `SessionContext` (Codex's probe shows a clone copies config/UDF maps and a bootstrap-restore can replace the shared default catalog; `new_with_state` also resets the creation timestamp)                                                                                                                                                                                                                                                                           |
| `PlanConfig` and flow `sql_conf` overrides | `SparkSession::plan_config_with_overrides(flow.sql_conf)` exactly as `analysis.rs:101` does. Revised: the unit-5 `EvaluationContext` today records only case, keys, sequencing text, delete condition and column selection; unit 4 extends the sealed identity with an **evaluation snapshot** (the resolved `PlanConfig` fields that change expression semantics: case sensitivity, ANSI mode, session time zone, the flow `sql_conf` overrides verbatim) and a **source-binding identity** (the intent id and, per bound source, its descriptor digest and the range list). Nothing is claimed to be in the seal until that struct carries it. |
| catalog manager and extensions             | the session's extensions are reachable through the derived state; no new catalog path                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| resource scope                             | Revised: the runner's existing preparation owner and its one existing `TaskResourceScope` cover preparation, lowering and execution of the attempt; lowering never creates a scope of its own. `TaskResourceScope::seal` only closes admission; `cancel` seals **and** latches cancellation. Cancelling an attempt means `cancel`, and the next attempt is a new owned attempt under the runner, not a scope minted in lowering                                                                                                                                                                                                                  |
| object-store routing for checkpoint writes | Codex's owned-effect adapter (`checkpoint-effect-adapter-design`); the batch context must carry whatever runtime-env overlay that design selects, which is why the context is derived by a single constructor owned with the execution code, not assembled in the streaming module                                                                                                                                                                                                                                                                                                                                                               |

Concretely: one operation-owned `BatchContext { ctx: &SessionContext, config:
Arc<PlanConfig>, scope: &TaskResourceScope /* the lease's */, intent: BatchIntent,
identity: InputIdentity }` built by one function in the execution module (Codex's side
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

| Operator                                                                                                                                                                                                          | Decision                                                                                                                                                                                                               | Reason                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Projection, Filter, Limit-less Union, scalar expressions whose every function signature is `Immutable`                                                                                                            | admit                                                                                                                                                                                                                  | row-local, replayable                                                                                                                                                                                                                                                                                                  |
| Join of a recorded range with a **static side** (a local batch output materialised before this batch, or a catalog table read at a pinned version)                                                                | admit, with the static side's identity in the evidence                                                                                                                                                                 | the static side does not change within the batch; the stream side is one range                                                                                                                                                                                                                                         |
| Join of two recorded ranges (stream-stream)                                                                                                                                                                       | **reject**, listed                                                                                                                                                                                                     | Revised: a key on the left in batch 1 and its match on the right in batch 2 needs cross-batch state; joining only the two current ranges misses it. The design review's "one batch over two ranges" describes range capture, not join semantics. Admitted only when the stateful contract exists, with reference tests |
| Projection or Filter calling any function whose signature is not `Immutable`: `Volatile` (`rand`, `uuid`) or `Stable` (`now`, `current_date`, `current_timestamp`, fixed per planned attempt, not across replays) | admit the plan, but mark the batch **non-replayable in content**: the unit-5 identity records the volatility and validation/dedup run once over one materialised evaluation, never re-evaluated under the same receipt | Revised: no broad scalar-UDF admission; evaluation must not differ between validation and dedup                                                                                                                                                                                                                        |
| Aggregate without watermark, Window, Sort, Limit, Distinct, stream-stream join with state across batches                                                                                                          | reject, listed                                                                                                                                                                                                         | AvailableNow aggregates and stream-stream joins need durable cross-batch state (handoff item 4); batch support of the operator does not establish streaming semantics                                                                                                                                                  |
| Repartition                                                                                                                                                                                                       | admit, noted                                                                                                                                                                                                           | no semantics; the private branch's removal is not ported                                                                                                                                                                                                                                                               |
| Auto CDC flow                                                                                                                                                                                                     | admit the source read only; the CDC steps run on the executed rows through units 2 and 5, not as plan operators                                                                                                        | validation must see original rows                                                                                                                                                                                                                                                                                      |
| Any `TableScan` not bound through `BoundedScope` (catalog table)                                                                                                                                                  | reject                                                                                                                                                                                                                 | would read outside the intent                                                                                                                                                                                                                                                                                          |

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
2. **No Iggy types cross the seam, and no dependency cycle.** Revised
   (CF-0053): `BoundedSource` currently lives in the private
   `sail-spark-connect::pipelines::streaming`, and `sail-data-source` cannot
   implement a trait from `sail-spark-connect` because `sail-spark-connect`,
   `sail-plan`, `sail-execution` and `sail-session` already depend on
   `sail-data-source`. The smallest protocol-neutral contract moves one layer
   down, to `sail-common-datafusion`, which both already depend on and which
   already has `serde`, `async-trait`, `datafusion` and the existing
   `streaming/{source.rs, event}` module:

   | Moves to `sail-common-datafusion/src/streaming/bounded.rs`                                                   | Stays in `sail-spark-connect::pipelines::streaming`                                      |
   | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
   | `Cursor`, `Incarnation`, `PartitionId`, `Partition`, `SourceDescriptor`, `Range` (serde types, no behaviour) | `RunFrontier`, `Progress`, `BatchIntent`, `next_intent`, `PlanError` (the control model) |
   | `ScanError` as a plain enum with `Display`; **no** Spark error conversion                                    | `impl From<ScanError> for SparkError`, `impl From<PlanError> for SparkError`             |
   | `#[async_trait] trait BoundedSource { schema; describe; earliest; frontier; plan_end (sync, pure); scan }`   | `DeterministicSource` (test adapter) and the tests                                       |

   Dependency edges after the move: `sail-common-datafusion` gains nothing;
   `sail-spark-connect` already depends on it; the Iggy adapter in
   `sail-data-source` (behind a new `iggy` feature, since the pinned sail-iggy
   feature is not in the current coordinator manifest) implements the trait
   and links the SDK there and only there. The adapter's cursors are
   `pos:<offset>` tokens and its incarnations the `PartitionContext.incarnation`
   rendered as a token. Implementation is one small unit: move the types,
   re-export them from the Connect module so existing tests keep their paths,
   convert the two `From` impls, and change nothing else; it is coordinated
   before editing because it touches a shared lower crate.

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

## 9. Prepared content authority: a C0 decision, not a patch

Codex's component probe (CF-0053) constructs two Arrow batches that compare
equal, ids `[1, 2]` with a nullable `Int64` payload `[10, null]`, whose hidden
physical values beneath the null cell differ. Both satisfy the non-null unique
key condition; `seal` produces different content digests and `verify` of the
equal batch fails with `ContentMismatch`. The unit-5 digest is therefore a
**physical IPC fingerprint after key ordering**, not a representation-
independent logical canonicalization. The behaviour is fail-closed, which is
the safe side, but it means the same logical rows can be refused on replay
depending on how an engine materialised them.

This is not patched by normalising `Int64` nulls: nested structs, lists,
dictionaries, sliced arrays and validity-masked values all carry physical
bytes that a logical comparison ignores. The C0 design must choose and version
one authority, with the other explicitly rejected:

| Option                          | Obligations                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A. Canonical logical encoding   | define a versioned encoding that writes only logical values (null cells as a null marker and nothing else; nested, list, dictionary-decoded and sliced arrays re-encoded densely); prove it with null/nested/dictionary/slice/offset tests on every supported type; reject types the encoding does not cover; the digest is then reconstruction-stable |
| B. Stored sealed-byte authority | the sealed rows themselves are staged durably (the design review's "publish an immutable reconciled-batch manifest") and recovery reads those bytes; `verify` compares the staged bytes' digest, never a reconstruction; reconstruction is permitted only as a cross-check that may fail closed but never certifies                                    |

Until that choice is recorded by Astra, the component keeps its present
fail-closed semantics, `B12` stays open, and no caller may treat a passing
`verify` of reconstructed rows as proof of logical equality. Codex has flagged
this checkpoint to the user.

## 10. Revision log

- Components as implemented on the Fable branch (CF-0136 scope, CF-0140,
  CF-0143, CF-0146, CF-0148 corrections): binding `ebf631edd` + `41f09ec47`,
  admission `2e9f098b2` + `1d570ae55`, lowering `9dc1b1157`. Beyond §10's
  first entry: binding names must be canonical (lower-cased, an output's
  spelling or `GraphScope::qualify`), and a `LocalBinding { name, identity,
provider }` describes the materialised relation a local read resolves to;
  admission verifies every `TableScan` by provider identity (range scans,
  static provider, local provider, or an empty scan the lowering minted for
  an empty intent) and rejects the schema-only `EmptyRelation` placeholder;
  join kinds follow `UnsupportedOperationChecker.scala:498–545` for one
  range-bearing side, and each subquery embedded in an expression counts as
  its own side; `lower` takes an `Inputs` struct (graph, flow, relations,
  sources, statics, locals) and borrows the preparation's scope without
  using it in this in-memory component. After CF-0155 (`a19f2ba2f`):
  `BoundedScope` dispatches on the validated read set, so a streaming read
  of a local streaming output uses its recorded ranges whatever the graph
  installed for that name; the snapshot carries the declared static and
  local identities read. Tracked gaps: mixed-mode reads (CF-0138);
  provider-implements-range and identity-pins-data at integration; the
  static side's pinned identity is caller-asserted; a local temporary view
  expanding to leaf providers under other scan names is not representable
  by `LocalBinding` and is rejected by admission (fixture), not supported.

- Revision after CF-0136 (component scope approved on the Fable branch), the
  boundaries the components are built to; where they narrow §2–§5, this
  entry wins:
  1. **No synthetic namespace.** CF-0136 observes the reserved qualified name
     is spellable through quoted identifiers. The initial components do not
     rewrite the plan at all: `BoundedScope` resolves a streaming-read name to
     its bound ranges and `GraphScope` resolves batch reads of local outputs,
     and a flow that reads the same name in both modes is **rejected** before
     resolution (`MixedReadModes`), disclosed as a limit of the initial
     subset. Bindings are minted per lowering (one `BoundedScope` per call)
     and every resolved `TableScan` is checked against the binding set in
     admission. Source identity is explicit and caller-supplied:
     `SourceBinding { name, schema, descriptor, intent, scans }` (the current
     `BatchIntent` carries ranges only; no DTO is added to the lower crate in
     this unit).
  2. **Static side must be proven.** A batch read of a non-local name is
     admitted only through a caller-supplied `StaticBinding { name, provider,
identity }`; any other catalog scan is rejected before resolution. One
     join rule: exactly one range-bearing side and one proven static side
     (a local output or a static binding); two range-bearing sides rejected;
     range-bearing is computed transitively through projections, aliases,
     subqueries and nested joins. Extension and unknown plans are rejected.
  3. **Pre-resolution validation fails before resolver I/O.** The walk over
     `spec::QueryPlan` (respecting CTE scopes as `is_streaming_query_plan`
     does) rejects, before `PlanResolver` runs: unbound streaming reads,
     unbound catalog reads, mixed-mode reads, time-travel reads
     (`ReadNamedTable.temporal`, `time_travel.rs:233` executes a helper
     plan), `Pivot` without explicit values (`pivoting.rs:227`), `Tail`
     (`limit.rs:93` executes a count), the `Stat*` nodes (`stat.rs:386`),
     `DataSource`/`Udtf`/`DynamicTable` reads, and (after CF-0192) an inline
     Python table function without a declared return type, whose schema
     `resolve_python_udtf_plan` infers by running the UDTF's `analyze` in
     Python during resolution (`query/udtf.rs`); a declared return type
     keeps its arguments classified. No target `WriteTo`,
     `MERGE`, checkpoint or acknowledgement in the lowerer.
  4. **Snapshot captured after admission, in `Lowered`.** `PlanConfig` is built
     inside lowering from the authoritative context with `flow.sql_conf`
     overrides; `Lowered.snapshot` records case sensitivity, ANSI mode,
     session time zone, the overrides verbatim, and per binding the name,
     the SHA-256 of the canonical descriptor JSON and the ranges. It does not
     claim to exhaust replay dependencies and changes nothing in the unit-5
     seal. Volatile expressions mark the evidence non-replayable; execution
     and sealing remain Codex's effect barrier and the open C0 policy. An
     empty recorded range lowers to an empty relation with the binding's
     schema after every scan's schema is checked equal to it; an absent
     binding is a rejection.
  5. **Replayability keys on the signature, not on `Volatile` alone.**
     CF-0181 found the admission check used `Expr::is_volatile()`, which
     tests `Volatility::Volatile` only, so DataFusion's `now`/`current_date`
     and Sail's `TimestampNow` (`current_timestamp`), all declared `Stable`,
     passed as replayable against §4. `Stable` holds within one query
     execution and is fixed at each attempt's planning time, so across
     separately planned attempts it is as non-replayable as `Volatile`.
     Correction: every scalar, aggregate and window function signature in
     an operator's expressions is inspected and any that is not `Immutable`
     marks the evidence non-replayable, with the function named in the
     evidence; no function is special-cased by name. Codex's test-only
     fixtures (`150611117`, split as `ca2038b94` in CF-0183) are replayed
     as independent cases beside an
     `Immutable` arithmetic control and an `Immutable` built-in (`abs`)
     control.

- Revision after CF-0125 (pre-planning lease design): `BatchContext` borrows
  the authoritative `SessionContext` instead of a `SessionState` clone; the
  scope it carries is the runner lease's; three finite owners per run named
  (graph analysis, run-level frontier/progress, one lease per batch attempt).

- After CF-0044: read mode bound before resolution through a reserved
  qualified name (§2); absent binding versus recorded empty intent (§2);
  stream-stream joins rejected until the stateful contract exists, static-side
  joins admitted with identity in evidence, volatile expressions marked and
  evaluated once (§4); evaluation snapshot and source-binding identity named
  as additions to the sealed identity rather than claimed present (§3);
  `seal` versus `cancel` corrected, one owned scope per attempt from the
  runner (§3); public dry run stays resolution/admission (§5); adapter calls
  owned by the attempt's scope with an explicit provider disposition (§6).
- After CF-0053: the bounded-source contract moves to
  `sail-common-datafusion::streaming::bounded` with the exact split and
  dependency edges (§6); the prepared content digest is named a physical
  fingerprint and the C0 authority choice is set out with both options'
  obligations (§9).
