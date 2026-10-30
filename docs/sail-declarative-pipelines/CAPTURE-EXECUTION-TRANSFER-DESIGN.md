# Captured Session transfer and analyzer access

Status: active Astra checkpoint, announced before this phase. Source reviewed on
Sail `0af4cfcbbbb465f2e2ca0262c7c73b0e7ed67513`, with boundary characterization
`e42e1be9614db3d1cf8b396b160910bcc215fda9` and native analyzer primitive
`ece5b6aed15462cbc54f18a6f72482f1f5e2ad51`. DataFusion 55.2.0. This continues
[pre-planning ownership](PRE-PLANNING-OWNERSHIP-DESIGN.md), not a new execution
framework. No public caller/cluster/effect migration is authorized by this draft.

## Observed boundary

`JobPreparation` exposes its admitted scope, control, finish/cancel and consuming
execute. The local implementation borrows its minting runner and owns a clone of
the authoritative SessionContext. Its execute deliberately derives TaskContext
late from that authority, then attaches the already-admitted resources.

The new characterization passes a ScopedSession to the actual physical-planner
interface, changes authority after capture, then uses existing dynamic bound
execution. It observes:

| Phase | target_partitions | registry store | resource owner |
| --- | --- | --- | --- |
| Captured physical planning | 7 | child | admitted owner |
| Existing bound execution | 9 | parent | same admitted owner |

This is expected legacy behavior, not a failed legacy contract. Existing late-
capture tests must stay unchanged. The test is source-pinned in the evidence
packet; 134 common-datafusion + 222 execution libraries and one optimized case
under ten joined load workers pass. It checks registry identity, not storage
mutation ownership or backend effects.

DataFusion SessionContext::state clones state and calls mark_start_execution;
SessionContext::task_ctx derives from the authoritative read-locked state. A
second authority capture is therefore not a way to preserve the first query
snapshot, including its execution properties. Use the selected snapshot's task
context when implementing the explicit path; do not rebuild a SessionContext or
copy an operation clone back into authority.

## Selected narrow analyzer primitive

ScopedSession::analyze consumes a LogicalPlan and calls the captured state's
analyzer.execute_and_check with that state's config_options and the same no-op
observer used by Sail's existing native paths. It does not call optimize, execute
a statement, create a context or install provider routing. Analyzer rules retain
their original objects; arbitrary external work captured inside custom rules is
not newly supervised by this helper.

Two tests use captured config7 after parent mutation to9. A constant Filter stays
present, an optimizer barrier records zero calls, and a custom analyzer failure
remains recoverable by standard source/downcast. Exact fmt/strict Clippy and
136 common-datafusion + 71 plan library tests pass. An unchanged-test optimizer
substitution control fails the success case while the typed-failure case passes.

Resolver adoption is a separate decision. Existing with_query_session accepts a
generic DataFusion Session, whose interface has no analyzer-only method. Do not
pretend ScopedSession is SessionState via as_any, substitute optimize, or silently
fall back to authority for a newly promised captured-analyzer mode. A typed opt-in
accessor/setter can expose this primitive while preserving the current generic
method's documented partial behavior. Its exact public shape is not selected yet.

## Preferred execution candidate for review

Prefer a consuming capture transition bound to the existing preparation rather
than an execute argument containing an arbitrary foreign Session or TaskContext.
The caller admits first, performs required authority mutations, then captures.
The captured object exposes a borrowed ScopedSession for resolution/analysis/
physical planning and consumes itself for execution. It retains existing control,
finish/cancel and independent cleanup reporting. Existing execute remains late-
capturing and unchanged.

Illustrative shape, **not an implemented or finalized Sail API**:

```rust
trait JobPreparation {
    fn capture<'a>(
        self: Box<Self>,
        registry: Option<Arc<dyn ObjectStoreRegistry>>,
    ) -> Result<Box<dyn CapturedJobPreparation + 'a>>
    where
        Self: 'a;
    // Existing execute and other methods stay available.
}
trait CapturedJobPreparation {
    fn session(&self) -> &ScopedSession;
    // Existing ownership/control operations, plus consuming execute.
}
```

A standalone Rust1.98.1 probe verifies only the language property: a lifetime-
generic consuming method can dispatch through a trait object and return a captured
object borrowing its runner; a second probe cannot move that object beyond the
runner lifetime (E0597). It is not a Sail implementation, async-trait/runtime test,
registry qualification or cluster serialization proof.

The optional registry is already qualified by its supplier, matching current
ScopedSession::with_object_store_registry. No default owned router or writer memory
policy is chosen here. Backends without capture support must explicitly report
unsupported; do not use the legacy execute path under a captured guarantee.

Before accepting this interface, check:

1. Capture failure and caller/RPC loss retain independently owned cleanup; preserve
   the typed primary outside that report. Obtain control before consuming capture
   if an error otherwise consumes the guard.
2. Stop before capture, during borrowed planning and before execute cannot invoke
   a refused physical factory. No detached planner, eager stream pump or new scope.
3. Capture stays one-shot; the captured session cannot accidentally be exchanged
   with another preparation. Keep the minting-runner borrow and existing job ID.
4. Execute derives the task context from the saved view, with the exact same
   resources, functions, config and runtime registry. No second authority capture.
5. Full state/registry/provider dependencies have sufficient lifetime through
   execution/disposal and registered I/O settlement. Do not infer this just from
   TaskContext identity or a successful empty-stream test.
6. The default unsupported path and cluster preparation are explicit before any
   generic caller migration. Driver-local SessionState/registry Arcs are not a
   worker transport format; preserve worker-side resource ownership and codecs.

## Provider lifetime facts and unresolved migration boundary

The initial source audit distinguishes objects and phases rather than treating
all providers as interchangeable:

| Path | Source observation | Qualification still required |
| --- | --- | --- |
| Delta create_delta_source | load_delta_read_state gets the factory Session's store, constructs a log store, and returns DeltaTableSource with snapshot/log_store | Which later planning/CDF/row-level paths still use that retained store after an analysis lease ends |
| Delta file-scan configuration | datasource/scan.rs resolves the data store from the supplied Session runtime and installs a reader factory | Execution-time reader/store lifetime and SDK children; not proved by logical metadata retention |
| Iceberg source creation | loads a Table with StoreContext, then constructs an IcebergScan containing metadata/snapshot and refinements | The temporary Table's metadata I/O and any relation/procedure paths retaining it |
| Iceberg scan planning | multiple scan paths reacquire their store from the supplied Session | Reader/task runtime propagation and cancellation/disposal across each path |

These are source observations, not live backend verdicts. In particular, do not
finish a graph-analysis owner, keep a logical plan containing an owner-bound store,
and assume it can run under a fresh attempt owner. Conversely, do not retain an
analysis scope forever to avoid that question. Audit actual native paths and the
three-owner lifecycle from the parent design: finite analysis, bounded-history
controller, fresh attempt/command. A drained scope is never reopened/reused.

Batch currently analyzes plans for later materialization; bounded lowering
re-resolves a flow over explicit bindings. Their migration/lifetime requirements
need separate caller traces. Whether an analyzed artifact can be reused, must be
rebound, or must be lowered again is not decided by the new method. External
static/local identity assertions and snapshot JSON remain incomplete backend-pin/
replay identity evidence. C0 representation and durable source/effect rules stay
open.

## Next review units

1. Commit/retain the observed legacy boundary and exact analyzer primitive with
   their source/gate/control evidence; no caller changes.
2. Review this capture candidate, native provider lifetime paths and error/drop
   transitions before implementing the bound capture transition.
3. Add captured execution tests alongside unchanged legacy tests, including config,
   registry and function preservation, owner/lifetime refusal and unpolled/drop/
   stop/error paths. Use held tasks rather than timing races; optimized CPU stress
   for concurrency changes.
4. Add a typed analyzer opt-in for the resolver; compare exact native rule/config/
   error behavior and prove no optimizer or authority mutation.
5. Qualify local/cluster capability and each caller individually before activating
   any public path. Earlier catalog/authority I/O, Python schema analysis, primary/
   cleanup transport, complete session shutdown and SDK/ORC/CDC work remain open.
