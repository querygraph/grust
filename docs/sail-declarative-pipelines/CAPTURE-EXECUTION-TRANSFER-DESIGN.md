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

Resolver opt-in is implemented at Sail17b8ac254. Existing with_query_session
accepts generic DataFusion Session, whose interface has no analyzer-only method;
it keeps authoritative native command analysis. New with_scoped_query_session
accepts ScopedSession and selects its exact analyzer. A private Generic/Scoped
enum prevents mixed provider/analyzer choices; the last setter wins, and child
persistent-view resolvers preserve the entire mode. Do not pretend ScopedSession
is SessionState via as_any, substitute optimize, or fall back from typed mode.

Delta generated-column replacement validation and procedure-predicate native
analysis use the shared helper. Seven tests cover captured config/rule identity,
optimizer-free constant Filter, typed cause, generic/legacy behavior, setter order
and actual generated-column/procedure paths. Exact fmt/strict Clippy/136+78
libraries pass. Unchanged authority-fallback control yields2pass/5fail; generic
cases pass and captured cases detect the regression. See the
[resolver packet](evidence/resolver-native-analyzer/README.md). No new scheduling
mechanism/stress claim or public caller/cluster/provider migration.

## Consuming execution transition

The implemented transition consumes the existing preparation; its execute
accepts no foreign Session or TaskContext.
The caller admits first, performs required authority mutations, then captures.
The captured object exposes a borrowed ScopedSession for resolution/analysis/
physical planning and consumes itself for execution. It retains existing control,
finish/cancel and independent cleanup reporting. Existing execute remains late-
capturing and unchanged.

Shared contract integrated at Sail16c43aa29; local support follows at
Sail7505e2ced. The public caller migration is still separate:

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
trait CapturedJobPreparation: JobPreparation {
    fn session(&self) -> &ScopedSession;
    // Inherits ownership/control operations and consuming execute.
}
```

A standalone Rust1.98.1 probe verifies only the language property: a lifetime-
generic consuming method can dispatch through a trait object and return a captured
object borrowing its runner; a second probe cannot move that object beyond the
runner lifetime (E0597). It is not a Sail implementation, async-trait/runtime test,
registry qualification or cluster serialization proof.

The supplied registry replaces the captured runtime registry wholesale; it must
resolve all stores needed by the plan, or explicitly compose with the parent.
It is not automatically merged. The registry is qualified by its supplier, matching current
ScopedSession::with_object_store_registry. No default owned router or writer memory
policy is chosen here. Backends without capture support must explicitly report
unsupported; do not use the legacy execute path under a captured guarantee.
The default consumes admission through cancel() before returning typed
NotImplemented to the caller. The retained control independently reports
cancellation/cleanup; unsupported capability is not an abandoned preparation.
For a supported backend's construction failure, explicitly use
StreamPreparation::fail with the typed error. A synchronous capture cannot await
completion/reap itself: the caller saves control first and awaits cleanup.
DataFusion's Shared(Arc<DataFusionError>) allows the same typed cause to be kept
in both the returned error and the cleanup report, without stringification.

Before accepting this interface, check:

1. Capture failure and caller/RPC loss retain independently owned cleanup; preserve
   the typed primary outside that report. Obtain control before consuming capture
   if an error otherwise consumes the guard.
2. Stop before capture, during borrowed planning and before execute cannot invoke
   a refused physical factory. No detached planner, eager stream pump or new scope.
3. Capture stays one-shot; the captured session cannot accidentally be exchanged
   with another preparation. Keep the minting-runner borrow and existing job ID. A second capture is
   unsupported and consumes/cancels the guard; retain control to observe cleanup.
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

The [batch migration trace](BATCH-PROVIDER-MIGRATION-DESIGN.md) distinguishes
analysis artifacts from execution's separate plan cache: only temporary views
retain full analysis plans; table and persisted-view outputs retain schemas.
Persisted-view publication extracts columns and stores SQL/metadata, while batch
execution starts a fresh map. That historical trace must not be read as an
analysis-time Delta provider scan from analyzed.relations. Since f0ac099e6,
analysis exports only schemas and native publication options, no LogicalPlan;
provider plans remain in its working set and drop before it returns. The actual execution
cache still retains temporary/read_output plans across commands and needs fresh
owner bindings before migration. Bounded lowering re-resolves over explicit
bindings. External static/local identity assertions and snapshot JSON remain
incomplete backend-pin/replay evidence. C0 and durable source/effect rules stay open.

## Response to Fable review CF-0209

Fable's source review (Grust8391b2ab) confirms the retained Delta log store is
used for log/CDF/commit I/O while file scans acquire the planning Session's store.
Reusing analysis-time Delta plans can split a table's reads/writes across store
lineages. The retained store is currently a plain Arc: draining an analysis scope
does not itself refuse its I/O. Require re-resolution/rebinding under the attempt
owner before migration; capture alone cannot fix this. Iceberg's audited scan paths
reacquire stores, but deletion-vector/metadata-relation paths still need tracing.

Workers derive TaskContext from their own SessionContext; driver-local registry
Arcs/config do not reach them through current codecs. Cluster capture remains
unsupported until worker-resolvable configuration and ownership are qualified.
Scope-ignoring factories and custom analyzer/optimizer callbacks do not gain
supervision from a Session wrapper. The native state-backed methods still use the
captured state's parent runtime; do not generalize store-free rule behavior to
arbitrary custom callbacks.

The synchronous contract preserves the caller's typed capability error separately
from cancellation/cleanup. The earlier candidate's Drop path retained that caller
error but wrongly reported abandonment as cleanup's primary. Explicit cancellation
corrects the unsupported transition. Local construction failures need fail(error).

Fable follow-up CF-0211 (Grust51ec2668) traces TaskContext's owned config,
including typed extensions, function maps and runtime. Local plan nodes own their
dependencies, and registered factories/futures are Send + 'static and moved into
the owned task. Cleanup owns the raw stream until disposal, then joins registered
tasks. Root source confirms scan_by_adds_exec rebuilds its lazy state from the
owned TaskContext config/runtime, not from a captured-state borrow. This supports
local capture without an extra whole-SessionState retention mechanism: derive
TaskContext from the snapshot while owned; execution/tasks own what they use.
Validate this with registry lifetime across disposal and held registered I/O;
it is not a live backend verdict or a guarantee for arbitrary scope-ignoring
providers. The Delta lineage issue is distinct and remains open. No public
migration, C5 scope expansion or Status policy is selected here.

## Implemented local unit

Sail7505e2ced captures authoritative state once after the caller's mutations,
constructs the supplied replacement registry and returns a runner-bound borrowed planning view.
A private execution helper derives TaskContext from the saved snapshot for this
path; None preserves legacy late capture. The same admitted scope, ID, tracing,
cancellation check, stream completion and fail/await/reap paths are reused.
Synchronous capture refusal/construction failure explicitly calls fail with a
Shared typed cause; the caller saves control for independent cleanup observation.

Tests retain the legacy7/child→9/parent behavior and add captured7/child→7/child.
Additional tests check stopped capture's identical cause Arc, stopped/unpolled
execution factory refusal, finish/cancel/drop with held registered cleanup, and
registry lifetime through raw-stream disposal and held task-owned I/O settlement.
Exact fmt/strict Clippy/136+228 libraries pass. Optimized filters run6 and9 cases
under CPU load, including unrelated codec cases; all workers joined. Source and
controls are in the [local packet](evidence/local-captured-execution/README.md).
No public caller, cluster, provider rebinding or default owned router changes.

Fable implementation review CF-0214 / Grust7d4bcb00 confirms construction,
cancellation and owned-dependency/drop paths by source. Rustdoc a74c3f429 makes
second-capture cancellation and complete replacement-registry requirements explicit.
Capture's panic branch has no dedicated fixture: the stopped-capture test qualifies
fail/error sharing only. Planning itself can still run after stop; only scope
registration and execution enforce refusal. Arbitrary scope-ignoring callbacks
remain outside that guarantee.

## Next review units

1. Commit/retain the observed legacy boundary and exact analyzer primitive with
   their source/gate/control evidence; no caller changes.
2. Consume Fable review of the implemented local capture and preserve the
   provider lifetime and cluster transport restrictions before caller activation.
3. Extend captured execution tests alongside unchanged legacy tests as callers
   and provider paths are migrated, including config,
   registry and function preservation, owner/lifetime refusal and unpolled/drop/
   stop/error paths. Use held tasks rather than timing races; optimized CPU stress
   for concurrency changes.
4. The typed analyzer opt-in and two command sites are implemented. Consume
   Fable review and qualify each caller before selecting it in public execution.
5. Qualify local/cluster capability and each caller individually before activating
   any public path. Earlier catalog/authority I/O, Python schema analysis, primary/
   cleanup transport, complete session shutdown and SDK/ORC/CDC work remain open.
