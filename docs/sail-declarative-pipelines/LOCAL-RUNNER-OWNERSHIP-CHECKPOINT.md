# Local-runner ownership checkpoint for Astra

Recorded 2026-10-30T04:07:06.849180+00:00. This refines W2c of the
[ownership proposal](ORC-WRITER-OWNERSHIP.md), after distributed monitor commit
`e02e4f712f2b597d2aba0d0f49138da60b40e5d3`. The user was notified before selecting the next
local ownership design. No local-runner implementation has been changed. The
[source packet](evidence/local-runner-checkpoint/README.md) captures the relevant
Sail and DataFusion sources; a separate read-only agent corroborated these paths.

## Observed source boundaries

LocalJobRunner checks an atomic stopped flag, traces a plan and calls
execute_stream with a session task context. Stop only sets the flag. The check
and construction have no common admission boundary. DataFusion execute_stream
synchronously calls plan.execute and documents stream destruction as its query
abort mechanism. Sail's RoundRobinReceiverStream Drop releases its receivers and
spawned tasks when the final output stream is dropped.

Session deletion awaits JobRunner.stop and then removes checkpoint objects. Its
comment explicitly relies on stopped tasks being unable to recreate objects.
The trait currently returns unit from stop. A repository search found two
implementations, LocalJobRunner and ClusterJobRunner, and one direct
runner().stop().await call site in the session deletion path. This is not a claim
that a change to the return contract is cost-free.

TaskResourceScope stores every registered resource until drainage; it is an
attempt scope, not a registry that retires completed jobs. Its shared drain can
survive a dropped waiter, but a scope alone does not own a query stream retained
by a consumer. If construction happens outside the admission lock, a separate preparation
completion handshake must cover execute_stream constructing the actual stream.

## Consequences to resolve before implementation

A map of scopes plus cancel/drain is insufficient: stop could return while an
unpolled stream remains alive, or while construction begun before stop has yet
to publish its stream. Subsequent checkpoint deletion could then race with work
that was never stopped. This is an inference from the source ordering, not a new
observed runtime failure.

The local job owner must retain both preparation/stream ownership and resource
cleanup completion. It must stop a job whose consumer never polls again, reject
admission after sealing, and preserve ownership when a stop waiter is dropped.
Remove completed jobs instead of retaining all historical handles. Preserve
original typed query and cleanup errors, including nonretryable commit uncertainty.

## Alternatives to compare, not yet selected

| Alternative | Pull behavior | Main obligations |
| --- | --- | --- |
| Shared job control owns the stream | Consumer polls through synchronized state; no extra batch forwarding | Stop/Drop can take the stream independently; do not await under the lock; catch poll/destruction panic without abandoning ownership; coordinate preparation |
| Request-driven supervisor owns the stream | One downstream demand permits one batch poll | Bounded request/response lifecycle, cancellation independent of consumer polling, no eager prefetch or retained extra batches, preparation and supervisor ownership |

Work a complete trace for admission racing stop, destruction racing a poll,
consumer Drop, resource failure after EOF, and dropped stop waiters before choosing.
Compare the per-batch lock or channel overhead and dependency footprint against
Sail's current local path. No performance claim is established by this source audit.

Decide what stop completion means when cleanup is unresolved. The current unit
return cannot convey a typed cleanup failure; merely logging and returning would
let session deletion interpret it as stopped. Consider the minimal shared return
contract/caller handling required to preserve that boundary, including the
cluster path. Do not silently weaken session checkpoint cleanup ordering.

## Required deterministic integration evidence

- Stop wins admission: execute_stream is never called and no effect starts.
- Preparation pauses after admission: stop cannot finish until construction,
  stream disposal and registered cleanup finish.
- EOF waits for cleanup without cancellation; failures and poll/Drop panics
  request cancellation and preserve typed causes and secondary diagnostics.
- Dropping an unpolled or partially consumed wrapper initiates cleanup; stop can
  dispose a live stream without waiting for its consumer to poll again.
- Dropping a pending stop waiter leaves admission sealed and cleanup owned;
  repeated/concurrent stop callers await the same completion.
- No batch is polled without downstream demand. Completed jobs do not grow the
  registry indefinitely; unresolved jobs remain owned.
- Session checkpoint deletion begins only after the selected stop-completion
  contract is satisfied, including unresolved-cleanup handling.

Use channels/latches for ordering and explicit source/consumer poll counters.
This checkpoint neither activates the ORC writer nor completes streaming/CDC
shutdown design. Native writer accounting and durable streaming progress retain
their separate design obligations. Independent ORC schema and CDC validation
work can proceed without selecting either local ownership alternative.

## Existing Grust and LakeCat reuse candidates

Recorded 2026-10-30T04:40:43.113296+00:00. The [pinned source inventory](evidence/local-lifecycle-reuse/README.md)
identifies Grust cancellation notification/child pruning, an owned unpolled queue
handoff, demand-driven stream control and caller-independent worker patterns.
None of the reviewed modules already supplies the full admission, stream ownership,
shared cleanup and completed-job retirement contract above. Their dependency and
semantic boundaries are recorded for Fable's design discussion. LakeCat's reviewed
outbox projection/acknowledgment is a separate durable event-delivery concern.
This bounded source audit ran no tests and selects neither local protocol nor a
new shared crate. Existing Sail task-resource drainage remains the foundation.
