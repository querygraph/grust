# Local stream ownership and remaining shutdown integration

This resolves the stream-owner alternative in the
[local-runner checkpoint](LOCAL-RUNNER-OWNERSHIP-CHECKPOINT.md). It selects shared
ownership with a temporary exclusive polling lease. It does not yet resolve or
implement the complete runner/session/cluster shutdown protocol. The [pinned
source audit](evidence/local-managed-stream-design/README.md) records the caller
and lifecycle boundaries. Component gates are recorded separately; this design
document itself is not a runtime verdict. The initial
implementation is a component in `sail-common-datafusion`, using the existing
TaskResourceScope, Tokio and Futures dependencies. No new Grust/LakeCat crate is
needed for this unit; the [reuse inventory](evidence/local-lifecycle-reuse/README.md)
records the existing candidates and their different contracts.

## Why polling stays with the consumer

Consider a consumer that polls a borrowed `next()` future once, receives Pending,
then abandons that future while retaining the stream. A background supervisor
cannot observe that borrowed-future destruction. If it retains the outstanding
request, an upstream wake can make it consume and retain a later batch even
though the consumer never polls again. A one-slot response channel bounds this
change but does not preserve Sail's current pull behavior.

The selected component calls upstream poll_next only within the consumer's own
poll. It never starts a batch-forwarding task and never copies or queues a batch.
Its mutex protects ownership transitions, not upstream execution. The consumer
takes the stream into a PollLease, unlocks, polls synchronously, and returns the
stream or hands it to cleanup. An upstream poll or destructor that never returns
still prevents completion; this is cooperative cancellation, not a latency bound.

## State and ownership

| State | Stream owner | Cancellation behavior |
| --- | --- | --- |
| Ready | Controller | Latch cancellation and transfer the stream to cleanup |
| Polling | Exclusive consumer lease | Latch cancellation; lease disposal follows when the synchronous poll returns |
| Draining | Independently owned cleanup task | Signal registered supervisors, retain ownership and await drainage |
| Terminal | No upstream stream; immutable completion report | Repeated waiters receive the same report |

The cancellation flag is monotone. At Pending or a successful batch, the lease
restores Ready only if cancellation has not won the ownership transition. On EOF,
error or cancellation it seals resource admission synchronously and transfers the
stream to cleanup. Successful EOF does not cancel admitted supervisors. A later
cancellation still reaches supervisors whose completion is pending.

The cleanup task drops the stream before awaiting resource completion, so a
stream-held sender or lease cannot keep its own cleanup pending. Poll and Drop
panics are caught separately. A recovery guard owns the stream before foreign
waker callbacks or discarded-batch destructors can run. Upstream methods, wake
callbacks and stream destruction run outside the controller mutex. The resource
scope also seals under its lock and sends cancellation notifications after unlock;
a reentrant listener must observe sealed admission without deadlocking.

Construction accepts an already-known SchemaRef rather than calling the accepted
stream's schema method. Preparation and its failure/panic handling remain the
future runner owner's responsibility. This avoids claiming that a prepared-stream
wrapper closes the earlier execute_stream-versus-stop admission race.

## Completion and failures

The cleanup task owns a completion guard before it is spawned. If the runtime
drops that task before its first poll or during drainage, the guard disposes what
it owns and publishes an explicit interrupted-cleanup error. It cannot report
clean completion without drainage. This distinguishes runtime loss from merely
dropping one completion waiter, which leaves cleanup running.

`cancel()` initiates cancellation and sealing; callers await `completion()` for
the terminal report. Its `result()` combines primary and cleanup failures, while
`cleanup_result()` reports cleanup-only failures. A failed or cancelled query
whose cleanup succeeds differs from a failed destructor or an unresolved resource
supervisor. DataFusion Shared/Collection errors and source
wrappers retain the original typed causes; unknown-commit errors remain visible
to the existing nonretryable classifier. Interrupted generic cleanup is not
mislabelled as a proven mutation or a successful stop. Future runner integration
must consult cleanup qualification, retain unresolved ownership/outcomes, and
prevent unsafe retry or checkpoint deletion.

## Reviewable implementation units

1. Resource-scope notification fix and synchronous noncanceling seal. A focused
   regression on unchanged production code must expose the old held-mutex wake;
   the fixed scope must reject reentrant admission on both Open and Closing paths.
2. Prepared-stream ownership component. Cover ordinary batches without copies or
   prefetch, unpolled cancellation, held-poll handoff, abandoned waiters, EOF with
   pending resources, late cancellation, typed failures, panics and runtime loss.
3. Local runner admission and preparation ownership. Seal job admission atomically
   against stop, cover construction begun before stop, retire finished jobs, and
   retain unresolved cleanup. Do not use an ever-growing attempt-resource scope
   as the session job registry.
4. Fallible stop and session deletion lifecycle. Keep the session unavailable
   while stopping, retain ownership independent of an RPC waiter, return actual
   deletion outcomes, and gate checkpoint deletion on qualified completion.
5. Audit and close the remaining effects/shutdown paths: existing spawned-task
   joins, checkpoint writes, manager-wide local shutdown, cluster task drainage,
   worker acknowledgements and driver completion. Each needs its own source and
   fault-injected evidence before claiming whole-session cleanup.

The caller audit found only one direct JobRunner.stop call, but that does not make
the complete change a one-line signature edit. Explicit deletion currently
acknowledges success and marks Deleted before its spawned stop task finishes; idle
deletion shares that helper. Manager-wide shutdown bypasses local runners and can
abort ordinary deletion tasks. Cluster shutdown_and_wait can return after a
mailbox closes while the original stop hook is still running, and worker/task
shutdown does not yet prove registered cleanup drainage. Existing typed error
conversions can carry stop errors without flattening them into strings.

Dropping DataFusion SpawnedTask handles requests abort without joining them. The
new component qualifies only its owned stream and registered resource supervisors;
it cannot establish that all legacy operator effects have stopped. In particular,
checkpoint registry sealing and deleting an object-store prefix must not race
with writes already admitted elsewhere. No new general catalog, streaming offset,
Iggy acknowledgement or CDC recovery guarantee follows from these components.

The full Spark4.2.1 SDP suites remain the acceptance target. These lifecycle units
are prerequisites for safe ORC/streaming effects, not substitutes for the original
pipeline assertions, public ORC writer qualification or streaming/CDC execution.

## Resource-scope sealing and cancellation notification

Recorded 2026-10-30T05:08:27.823650+00:00. [Sail `5fc71b3792`](evidence/scope-notification/README.md)
passes 87 library tests, formatting and strict Clippy; 9 focused tests
also pass in an optimized build under CPU load. Exact receipts and limitations
are retained. This is a lifecycle foundation; local runner/session/cluster
integration, public ORC writing and full streaming/CDC acceptance remain open.

## Prepared-stream ownership and registered cleanup

Recorded 2026-10-30T05:08:27.857230+00:00. [Sail `f3d32b8959`](evidence/managed-stream/README.md)
passes 99 library tests, formatting and strict Clippy; 12 focused tests
also pass in an optimized build under CPU load. Exact receipts and limitations
are retained. This is a lifecycle foundation; local runner/session/cluster
integration, public ORC writing and full streaming/CDC acceptance remain open.
