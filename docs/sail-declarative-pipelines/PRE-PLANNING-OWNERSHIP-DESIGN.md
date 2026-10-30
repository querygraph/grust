# Ownership before planning: preparation leases and session authority

Status: active design checkpoint, announced to the user for Astra. Source base
Sail `bebabdb9e7ef7d072ea39f9ec9ac536af86a3f50`, DataFusion55.2.0 and
object_store0.13.2. The finite-job lease lifecycle, caller-owned cancellation and
local bound preparation API are implemented below. Planning callers, cluster
preparation, complete context overlay, handled-effect policy and writer memory
mechanism remain open. This is not a full session/cluster/SDP verdict.

Continues [provider/runtime ownership](PROVIDER-RUNTIME-OWNERSHIP-DESIGN.md),
[stream preparation](LOCAL-STREAM-OWNERSHIP-DESIGN.md), and the
[actual writer trace](evidence/checkpoint-writer-errors/routing-followup.md).

## Observations that constrain the hook

JobRunner.execute accepts an already-created physical plan. On this historical base, LocalJobRunner creates
ScopedTaskContext, StreamPreparation and admission only after that call begins.
The later bound API below permits earlier admission; existing planning callers
still use the legacy entry and remain outside that coverage. Earlier resolver, DataFrame and physical-planner work is outside that
admission. Worker task preparation is different: its fresh task scope already
precedes decoded-plan preparation and TaskMonitor execution. Do not transfer the
local observation into an unsupported whole-cluster claim.

Resolver planning includes more than metadata reads: query/pivoting.rs and
query/time_travel.rs execute helper plans through ctx.execute_logical_plan(...)
and collect(), before JobRunner admission. Data-source read/write/procedure/row-
level factories also receive ctx.state() snapshots. A runtime overlay attached only
to final physical execution would miss those paths. The explicit operation-state
candidate must cover helper execution as well as schema/provider construction.

The direct runner-use inventory on the source base is:

| Site | Ownership work required |
| --- | --- |
| Spark Connect handle_execute_plan | Admit before handle_sql_config and planning; preserve its authoritative config path and returned schema |
| Connect streaming query start | Admit before resolution; transfer into the actual query stream and query registry |
| SDP run_command | One finite preparation/job lease per metadata/write command; retain caller RelationScope borrows |
| Flight service query | Admit before native statement resolution/execution; preserve session config effects |
| function gold-test helper | Migrate the same preparation path; a test-only bypass must not qualify production |
| EXPLAIN runner.explain | No job execution admission implied; physical EXPLAIN planning can still perform provider work |
| session stop_and_clean_checkpoints | Existing runner.stop must still observe admitted preparation before cleanup can run |

Graph analysis and materialize.tables also perform metadata reads outside individual
run_command calls. Distinguish three owners: a finite graph-analysis lease; a
stop-visible run controller for frontier/progress I/O that precedes and outlives
batches; and one finite preparation/execution lease per batch attempt or command.
The run controller must retire joined child-call/attempt records; it is not a
resource scope that accumulates every I/O handle for the run's entire lifetime.
A retry gets a new lease, never a reopened or drained one. One TaskResourceScope cannot be reused across sequential jobs after
its first drainage seals it. The session job registry is not an ever-growing
resource scope; preserve the existing retirement of joined history.

## Experiment: a cloned SessionContext is not an authority-preserving wrapper

[Source-pinned probe](evidence/planning-context-design-probe/README.md), detached
candidate `27b82ad2588696973a232660e2affcb8153409a3`, observes three cases:

1. new_from_existing shares the catalog list, generates a new session ID by
   default and suppresses default-catalog creation, but copies session config and
   DataFusion UDF maps. A child table registration is visible in the parent;
   native SetVariable changes child target_partitions from7 to9 while the parent
   stays7; a DataFusion child UDF registration is not visible in the parent.
2. Restoring the original config before build re-enables catalog bootstrap.
   The shared default catalog is replaced and an existing parent table disappears.
3. Setting the original session ID before build and restoring config after build
   avoids that bootstrap overwrite and preserves existing runtime/UDF Arcs, but
   still yields a separate SessionState Arc. Native SET still changes only the child.

Sail's ServerSessionFactory intentionally disables default catalog/schema creation,
uses CatalogManager, and does not add DataFusion default features. Worker sessions
do add default features. The bootstrap counterexample is therefore a default/
custom-context compatibility hazard, not an observed catalog loss in Sail's normal
server configuration. Do not 'fix' a server snapshot by adding default functions
or changing that catalog policy.

This is dependency characterization, not a proposed production helper. Sail uses
its own SQL parser; the initial probe's SessionContext.sql call did not compile
because that DataFusion SQL feature is disabled. The corrected probe uses the
same native LogicalPlan::Statement path as Sail. Sail CatalogManager function
registration uses its own shared manager state, so the DataFusion-UDF observation
must not be generalized into a claim that every Sail function command is lost.

Decision: reject generic replacement of the authoritative SessionContext with an
operation clone, and reject copying child state back wholesale. The latter can
clobber concurrent config changes, function registrations and custom runtime state.
Do not temporarily swap a globally shared runtime/registry around planning.

A candidate that avoids a new SessionContext is to retain the authoritative
context while passing a separate operation SessionState to query factories,
physical planning and helper-query execution. That requires a deliberate resolver
state seam and caller audit, not replacing every authority access blindly.
SessionStateBuilder::from(SessionState) delegates to new_from_existing in this
version; switching constructor spelling does not avoid the observed behavior.

A query snapshot may use the builder's bootstrap-safe sequence plus explicit ID,
complete config/extensions, planner/optimizer/registry preservation and a private
RuntimeEnv overlay. It must remain a snapshot: authoritative session commands need
an explicit authority path. SessionContext::new_with_state also resets its context
creation timestamp; that is an additional source-level preservation obligation,
not something established by the three probe assertions.

## Selected lifecycle direction: an explicit finite preparation lease

Admission must be published in the runner's stop-visible registry before invoking
any callback that can resolve, construct a DataFrame or prepare a physical plan.
The lease is move-only. It owns the existing resource scope and StreamPreparation;
it is not a second scope created while lowering. It moves exactly once into either
stream execution or preparation-failure/abandonment cleanup.

The caller polls planning, retaining borrowed RelationScope/config data on its
current task. It selects planning against a latched cancellation-request future.
When cancellation wins, drop the planning future before releasing the preparation
guard, then await qualified cleanup when a response can still be delivered.
Caller/RPC loss drops the guard; its independently owned cleanup still runs. A
foreign synchronous poll/destructor that never returns remains a cooperative
cancellation limitation; do not report bounded termination from this design.

Adapter work started by lowering must be admitted through the lease before any
provider invocation. Lowering borrows the lease's scope and returns plan plus
admission/identity evidence; it neither manufactures a scope nor seals it. A raw
asynchronously disposable provider cannot be smuggled through the completed-value
run API. Creation, retention and settlement must have the appropriate supervisor.

A held-planning test must also hold an admitted adapter task on its actual I/O
runtime. Dropping the borrowed planning future drops its result receiver; it does
not stop that task. Release the planning guard, observe completion still pending,
then settle the task and inspect the report. The run controller must retain that
report for attempt/progress policy. A cancelled/interrupted attempt and confirmed
cleanup are separate facts; no frontier advancement or proof of rollback follows
from a cancelled waiter or from cleanup alone.

The cancellation observer does not seal or drain on observation. Noncanceling seal
must not satisfy it, and observing cancellation must not become proof of joined
storage effects. Preserve current pull-driven execution; no detached planner or
batch-forwarding task is introduced merely to make lifetimes 'static.

Selected API shape: the preparation object is itself the bound executor. The
caller never passes it back to an arbitrary runner. Its private implementation
borrows the minting runner and retains the admitted job identity; consuming the object prevents
duplicate execution, and there is no cross-runner argument to accidentally accept.
The common object-safe surface under review is:

```rust
#[tonic::async_trait]
trait JobPreparation: Send + Sync {
    fn resources(&self) -> &Arc<TaskResourceScope>;
    fn control(&self) -> ManagedStreamControl;
    fn finish(self: Box<Self>) -> ManagedStreamControl;
    fn cancel(self: Box<Self>) -> ManagedStreamControl;
    async fn execute(
        self: Box<Self>,
        plan: Arc<dyn ExecutionPlan>,
    ) -> Result<SendableRecordBatchStream>;
}
// fn begin_preparation(&self, ctx: &SessionContext)
//     -> Result<Box<dyn JobPreparation + '_>>
```

Implemented in Sail `a0a369baada5b3b78d66c11c6694191da72d6fe8` after helper
`18bfee751f61c06a1597ead382de72f11ceae4dd`: the trait is object-safe and its object
lifetime borrows the minting runner. No Arc-core refactor is needed. begin publishes
admission before returning, stores an authoritative SessionContext clone sharing
state and does not freeze config. execute captures TaskContext late and attaches
the exact admitted owner. Legacy local execute delegates through this object.
Cluster/other runners keep legacy execute and default to unsupported preparation;
no generic planning caller has migrated. [Evidence](evidence/local-bound-preparation/README.md)
qualifies the local lifecycle, late config-state mutation and legacy regressions.
The operation capture/freeze boundary and private state still need an explicit API;
late capture alone does not establish per-query isolation against concurrent SET.

The typed primary result stays with the caller; finish/cancel take no error input.
The returned control supplies cleanup observation, while cancel's control outcome
is cancellation. StreamPreparation's new no-stream finish/cancel operations are
the corresponding lower seam: finish seals without cancellation; cancel latches
cancellation; neither manufactures a stream or coerces a caller's error. A prior
cancellation cannot be cleared by finishing. Simultaneous primary/cleanup failures
still need their transport policy; returning control is not permission to ignore
its cleanup result. Legacy execute remains a compatibility entry for already-
prepared plans and cannot claim ownership of earlier planning.

Keep the admission owner in the existing runner lifecycle rather than introducing
an unobserved JobService side registry whose work runner.stop would miss. A cluster
implementation must own coordinator preparation and request remote shutdown before
waiting on work that depends on it. It cannot serialize an Arc<TaskResourceScope>
or silently create local-only coverage while claiming worker ownership. Worker
scopes remain per attempt and need their own codec/task/driver qualification.

Primary planning errors and cleanup outcomes must remain distinct typed values.
The lease must not return the first display string, lose a structured Spark error,
or convert a cleanly joined ordinary analysis failure into an unresolved effect.
An abandoned preparation still differs from an owner that confirmed backend cleanup.
The local bound object and no-stream exits now exist. Typed primary/cleanup
transport, general context propagation and cluster ownership remain next work;
the component gates do not qualify those absent caller paths.

## Session authority and snapshot rules still needing an exact API

Admit before Connect handle_sql_config; run the existing authoritative native/Spark
config mutation against its authoritative context, then capture the resulting
planning configuration at the current semantic phase. Flight/native SET needs the
same explicit treatment. No new command whitelist may silently execute unknown
session mutations against an ephemeral snapshot.

For bounded unit-4 lowering, retain PlanResolver::new on the authoritative context
with flow.sql_conf represented as PlanConfig overrides, and pass the lease's scope
separately to owned adapter callbacks. No new SessionContext is required there.
This explicit adapter route does not intercept arbitrary catalog/file-planning I/O
that still reads the parent's runtime; general planning-overlay coverage remains
an exact API obligation, not a consequence of that lowering signature.

Graph analysis must keep its typed SparkError::UnresolvedPipeline value available
to the existing post-select flow-event emitter; automatic Context/External boxing
inside a generic lease would change that match and its Status mapping. Let the
caller retain its typed primary result independently of cleanup observation.
The combined-primary-and-cleanup failure policy still needs an explicit API and
transport gate; merely boxing both or retaining only the first message is not it.

Preserve flow.sql_conf overrides, existing CatalogManager authority, final custom
runtime/state mutators, all four function maps and actual catalog bindings. Builder
cloning does not establish an atomic snapshot across remote catalogs or independent
SparkSession/CatalogManager locks. State the actual capture boundary; do not invent
snapshot isolation. Final registry identity must be the one routed, not a stale
factory default. PlanResolver/RelationScope stay Sail's resolution mechanisms.

## Effect outcomes: keep evidence, do not infer settlement from condition names

The current facade preserves AlreadyExists/Precondition for callers and retains
failed mutation reports. Those condition names alone must not clear a scope failure:
a provider retry after a lost successful response can return a condition failure.
A generic retrospective 'acknowledge this error' would erase uncertainty without
proving the effect outcome. No such API is selected.

An enclosing transactional protocol can eventually supply an explicit, typed
outcome/receipt that distinguishes operation failure from confirmed effect
settlement and retained cleanup failure. That protocol must preserve the original
attempt/error history, identity, stage and unknown results independently of waiter
loss. It cannot just return Err inside Ok so the drain looks clean. The exact
receipt/adjudication API needs its own provider/transaction experiments before
changing TaskResourceScope's existing failure semantics.

First routing must therefore preserve failures and retain unresolved namespaces;
it must not advertise handled-conflict transactions as qualified success. Successful
batch/checkpoint execution is still required; conservative failure handling is a
staging boundary, not the goal's final acceptance definition.

## Burst and byte bounds: no arbitrary part-count default

The actual writer experiment showed why BufWriter's nominal concurrency8 is not
a burst bound: WriteMultipart.write/put synchronously queues every full chunk in
one call. One-byte chunks with a one-part facade fail AtCapacity. The separate
refusal test joins abort and publishes nothing; the successful two-row fixture's
256-byte/eight-part envelope is not a production setting.

Do not install an arbitrary larger semaphore limit as the solution. A production
mechanism must account for active work, queued payloads, single-call bursts and
backing allocations retained by Bytes/Arrow slices; payload length alone does not
bound retained allocation. Possible mechanisms needing proof are a bounded writer
fragmentation seam, or ordered deferred part admission with explicit memory
reservations and cancellation ownership. Either must preserve part index order,
parallelism, typed errors and existing runtime affinity. DataFusion's internal
ParquetSink creates its writer privately; a facade cannot pretend to intercept
AsyncWrite before that point. No mechanism is selected by this note.

## Incremental implementation and acceptance order

1. Implemented: latched cancellation observation, borrowed/registered-I/O model,
   and no-stream preparation finish/cancel. These are component seams, not runner
   admission or planning routing.
2. Resolve the exact lease/handoff API with finite local admission/stop tests:
   held planning entered before stop, stop before admission, dropped RPC, panic,
   ordinary failure with clean cleanup, and already-admitted mutation settlement.
3. Build the query snapshot helper only after full preservation tests and explicit
   authority routing for session mutations. Preserve builder/bootstrap counterexamples.
4. Wire Connect, Flight and SDP call sites individually, including graph analysis
   ownership and per-command jobs. Test native SET/functions/catalog visibility,
   custom mutators, no eager input polling and original structured errors. Do not
   grant cleanup-qualified deletion from admission-only prototypes before unit5.
5. Select and qualify actual writer burst/memory admission and effect-outcome
   contracts before production installation; then route checkpoint sink lookups,
   metadata and compensation. Keep successful writes in the acceptance gates.
6. Extend coordinator/worker/driver/session teardown with cancellation requests
   before dependent joins and truthful terminal acknowledgements. Qualify original
   Spark4.2.1 SDP behavior; no helper or partial public selection substitutes for it.


## Review state

Fable CF-0127 accepts the borrowed, single-attempt lease direction for unit4 and
adds the run-level frontier owner, sealed-before-provider admission, exact typed
analysis-error preservation and the registered-I/O counterexample above. These
constraints are incorporated; no new shared edit or async source API is approved
by their incorporation. The exact runner/handoff/session-authority API remains
the next design task. Independent source/transport review of Fable's event stack
continues separately; its reported green gates do not integrate that branch.
