# Live source capability and control: design assessment

Reviewed 2026-11-06T10:14:59.718530+00:00, before dependent implementation. Read the full saved request,
grust-sdp AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and source
.github/copilot-instructions.md. The applicable source checkout has no additional
AGENTS/CLAUDE instruction file. Source starts detached at
`b6d73d6a644dc04b1e6749e171100808c874d788` in
`/Users/alexy/src/sail/tmp/source-control-20261106-b6d73d6a`; upstream base is
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Observed upstream `ae21b2ef7`
is a separate inspection target, not a qualified integration claim.

The full SDP, native Extensions and Comet, performance, mandatory fencing,
recovery, typed configuration and optional Dhall goal remains active. This report
recommends a coherent source-control increment without substituting static types
or a remembered source classification for actual running-source integration.
Only this assigned report is written. No source edits, builds, runtime tests,
remote actions or cleanup were performed.

## Existing ownership, inspected in source

StreamSource::scan produces an ExecutionPlan; it does not own its eventual live
reader. RateSourceExec constructs BatchGenerator inside execute. Its counter and
current-time timestamps are execution-local. The physical codec reconstructs a new
rate plan from options/schema/projection on workers. A planner-held StreamSource
object cannot control that reader. Existing rate/socket behavior does not establish
replay-safe recovery.

LocalJobRunner allocates a job number, traces the plan and calls execute_stream
with ctx.task_ctx. It has no driver and its current stop only refuses future jobs.
ClusterJobRunner submits a plan/context to the existing driver. The scheduler
assigns TaskKey with job, stage, partition and attempt; TaskPreparation reconstructs
a separate executable plan per attempt and calls execute with that exact key.
WorkerServer currently forwards one shared worker TaskContext to all attempts.
An attempt-specific extension cannot safely be inserted into that shared context.

TaskRunnerActor already owns admission, stop signals, job closure and task reports.
TaskMonitor drops its stream on cancellation/terminal/error and reports typed
causes. TaskRegistry records admission history, cancellation and closed jobs;
admitted keys remain historical until job closure. Presence in that set does not
prove a live source endpoint. Driver assignment and current task state provide the
existing route for checking which attempt is current. Reuse those owners.

## Recommended architectural seam

Actor ownership and TaskContext capabilities are complementary. Keep lifecycle and
routing in the existing job runner/task actors; use a typed TaskContext extension
to pass a fresh attempt-owned registration capability to the executing source.
This does not require a second coordinator, local driver or globally mutable
session registry.

Mint the scope before task preparation begins. TaskPreparation has the exact
TaskKey and is the natural injection point. A small scope can own bounded endpoint
registration and revocation while the actor holds the authoritative scope handle.
Source execute registers its actual endpoint synchronously through that capability;
actor commands route through the scope without blocking the actor on source work.
Local execution should own the analogous scope directly and tie it to returned
stream lifetime, preserving its driver-free execution.

TaskContext is not Clone, but public constructors/getters expose the configuration,
all scalar/higher-order/aggregate/window registries and runtime. Reconstruct the
per-attempt context with those exact values and its extension instead of owning a
DataFusion fork or mutating worker-wide state. Preserve memory pools, object stores,
function identities and query configuration. The common-datafusion layer can define
the typed registration capability; execution maps TaskKey to the scope. Avoid a
dependency cycle or duplicate scheduler identity structs merely to expose a mailbox.

Expose a genuine control handle through an admitted runner path. A channel only
reachable by test helpers, or a typed descriptor with no running endpoint, is not
this increment's intended integration. Remote claims require the actual driver-to-
worker/task route and fresh decoded plan, not just an in-process trait invocation.

## Identity and honest capabilities

Separate compiled source occurrence, live endpoint registration and durable source
identity. StreamSourceWrapper's Arc token is local optimizer identity and is absent
from the rate codec. It cannot identify a worker reader after reconstruction or a
source after restart. Two reads of one provider can be distinct participants.

For transient live control, an owner-minted scope and distinct endpoint registration
token can suffice if explicitly confined to that running attempt. If the owner must
address a pre-known source across codec reconstruction, add a compiled occurrence
identifier to the physical codec; display names or provider pointers are insufficient.
Neither token is a durable flow/source/incarnation identity. Do not put runtime
allocation order into a prepared recovery record.

Keep recovery capability optional and truthful. Rate timestamps use Utc::now and
its offset resets on execute, so position counters alone cannot promise identical
replay. A live ordered marker/cut control can be useful protocol progress while
still declaring recovery unsupported. Broker/storage descriptors must later define
incarnation, position meaning, retention, partition discovery and coordinated end
bounds before durable recovery admission. Do not invent those guarantees as enum
variants without an implementation.

## Cancellation, stale attempts and ordered acknowledgements

Close/revoke the attempt scope before signaling cancellation or job closure. Also
revoke on successful end, failure, panic, dropped output, abandoned preparation and
runner shutdown. A source registering after a blocked preparation races cancellation
must receive Closed rather than create a leaked endpoint. Local stop's current
future-admission behavior alone is insufficient to revoke existing control handles.

Registry removal is not enough when a sender or command has already been cloned.
Validate scope/registration lifetime at source dequeue/application, and validate the
expected current attempt again when the owner accepts a reply. An old registration's
cleanup must not remove its replacement. Replayed launch, duplicate registration,
late old-attempt error and an old queued acknowledgement must remain distinguishable.
Do not credit a replacement merely because job/stage/source names happen to match.

Define the acknowledgement boundary. Router acceptance, command application,
ordered marker emission and durable checkpoint completion are separate events.
A source cut must bind the actual reader position and previously emitted data at
the documented source boundary. A queued marker is not a committed checkpoint;
a control reply is not distributed alignment or target fencing.

A sleeping source should service controls while data is pending. Pausing reads
must not pause the control/cancel channel. Backpressured or completely unpolled
execution cannot claim an emitted-marker acknowledgement without downstream demand.
A future control task must not poll the data reader independently and reorder data
around a marker. Preserve one reader owner and the event sequence.

## Resource and error obligations

Bound endpoint registrations by active plan/partition counts and bound command
queues and outstanding requests. Start with serialized requests if that simplifies
the proof. Avoid unbounded duplicate-receipt history, endpoint history or payloads.
Actor handlers must never wait on source replies or hold a registry lock across
await. Return Busy, NotReady, Unsupported and Closed explicitly as appropriate.

Specify retry/duplicate identity and timeout behavior. A timed-out applied command
is not proven unapplied; issuing a fresh identity can insert a second cut. Either
retain a bounded retryable receipt for the current request or make uncertainty an
explicit outcome. A dropped waiter must not retain the source forever. Source EOF
or failure must close endpoints and settle pending controls; errors cannot be
relabelled success. Unsupported recovery must leave ordinary nonrecoverable
streaming usable. Keep the disabled-control data path cheap and measure the enabled
path rather than adding a control-channel allocation on every data batch.

## Coherent increment and verification

Before code, the root's self-contained plan should choose the live command,
capability scope, registration address, public runner entrance, acknowledgement
boundary, cancellation/timeout policy and exact local/remote admission boundary.
Those choices constrain code. Durable position preparation, transport alignment
and target effects remain later contracts, not implicit success of this unit.

The smallest meaningful increment exercises a real running source through the
selected runner, processes an ordered live command, and revokes it through the
existing lifecycle. Verify source scan/execute/poll counters, exact marker/data order
and source errors. Include a zero-rate pending reader, two occurrences/partitions,
control before readiness, bounded queue exhaustion, duplicate requests, cancellation
before registration, after enqueue and after application, terminal/drop cleanup,
and replaced attempt with late command/reply. Use controlled channels, not sleeps.

For remote admission, encode and decode the source, execute under a real TaskKey,
route through existing actor/RPC placement and show that the planning object is
not the live reader. A local TaskContext test alone does not establish worker
routing. Independently verify unsupported sources and ordinary batch jobs retain
their previous data behavior, and measure registration/disabled-control overhead.

Initial design verdict: combine existing-owner lifecycle with per-attempt capability
transport, rather than choose a parallel coordinator or a session-global mailbox.
This advances the actual runtime seam required by source recovery while preserving
honest capability and evidence boundaries. No implementation or readiness verdict
is issued before the root's plan and discriminating integration controls.


## Concrete before-code plan: local live contract first

Reviewed 2026-11-06T10:27:20.548265+00:00. Read SOURCE-CONTROL.md end to end without relying on its
supporting links. Source remains unchanged apart from review artifacts. This is
assessment of the concrete first increment, not a source implementation verdict.

The local-first increment is coherent progress toward the full goal. It includes
a common typed live-barrier contract, an actually usable controlled LocalJobRunner
execution handle, fresh runtime scope, physical source binding/codec, native rate
command polling, bounded pending/result state and closure guards. This is materially
more than a descriptor or test-only mailbox. Qualifying cancellation/order/request
semantics before freezing driver/worker wire fields is a reasonable dependency.
Explicit refusal by the new controlled cluster API preserves that boundary; ordinary
cluster execution must retain its established path. Distributed attempt routing
remains required follow-up work, and this unit must not be presented as completing
S1, distributed checkpoints or source recovery.

The plan supplies the context, alternatives, existing Sail fit and evidence boundary
within the document. Its capability distinctions are sound: compiled occurrence UUID,
per-execution scope and registration token address live execution, while the rate
ordinal is explicitly nonreplayable. It preserves the original source's wall-clock
timestamp/reset behavior instead of inventing a durable position. Sharing the
contract with future actor routing is preferable to either a local driver or a
second checkpoint coordinator.

Before implementation, resolve these lifecycle/API details explicitly:

- LIMIT zero can remain NotReady while its execution scope is open, because its
  source never executes. Output EOF/drop must subsequently close that scope; the
  wording that it stays NotReady should not imply immortal registry entries.
- Distinguish cancellation before application, during encoded handoff and after
  successful acknowledgement. Close must settle the receipt even when the source
  has dequeued its command. The scope must retain enough bounded shared operation
  state to arbitrate success versus closure under one registration identity.
- Define requests after closure, including retry of the latest completed ID.
  Returning Closed for new requests must not mutate an already completed receipt
  into a different historical outcome. Conversely, observing a prior live receipt
  must never be treated as a receipt from a replacement scope.
- Encoding must succeed before success becomes observable. State precisely that
  handoff is commitment to the source's current output poll, rather than downstream
  consumption or durable publication. An encoder error cannot leave a successful
  control receipt or an unbounded pending waiter.
- SourceController ownership must not let cloned controllers outlive output
  cancellation with still-active endpoints. Dropping a waiter must retain the same
  operation for retry without retaining all old requests. Dropping the controller
  alone should have an explicitly stated effect on the still-owned data output.

Validate and bound the expected manifest before source registration. Unknown IDs,
invalid partitions, duplicate bindings/partitions and unsupported capability must
have deterministic outcomes. Test two distinct logical reads of one provider and
a compiled bound subtree reused twice: shared physical Arc identity must not
silently coalesce two separately executed readers. Reject a duplicate compiled
occurrence topology or give each actual occurrence its own binding before execution.
An empty manifest/registry cannot accidentally satisfy an all-participants barrier.

Retain the fairness and demand boundary in the plan. Zero-rate sleeping readers
must wake for commands. Repeated barriers cannot starve a ready data deadline.
No output demand means no emitted-boundary acknowledgement; a separate waiter API
allows the caller to drive output without deadlocking on its own request. Busy,
NotReady, Unsupported, Stale and Closed remain distinct; a timeout does not authorize
a fresh operation ID. One pending request plus latest result is a reasonable bounded
starting policy, provided dequeued work is still covered by cancellation.

The transparent binding's schema/properties are necessary but not sufficient for
ordinary behavior. An extra physical wrapper can change optimizer pushdown,
operator-ID attribution or codec handling even when it forwards execute directly.
Preserve ordinary rate/socket plan, output, codec and cost controls; delegate any
required optimizer behavior rather than infer transparency from equal properties.
Keep the disabled native rate path unchanged and avoid channel work per data row.
Reconstructed TaskContext must retain every function registry/runtime/configuration
extension, including higher-order functions, without altering the base context.

Concrete-plan verdict: suitable for the authorized local reference increment once
these boundary choices are explicit and covered by real runner/source controls.
Local qualification is an integration step toward the common distributed protocol,
not a waiver of the latter. No builds, tests or source edits were performed; only
this assigned report was appended.
